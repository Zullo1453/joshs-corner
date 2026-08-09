"""Manual, provider-neutral flight search with a credential-gated Amadeus adapter."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from flask import current_app

from .extensions import db
from .models import AutomationRun, FlightOffer, FlightTracker, utc_now


class FlightProviderError(Exception):
    def __str__(self) -> str:
        return self.safe_message

    safe_message = "Check failed · provider temporarily unavailable."


class ProviderNotConfigured(FlightProviderError):
    safe_message = "Flight provider not configured."


class ProviderAuthenticationError(FlightProviderError):
    safe_message = "Check failed · provider authentication needs attention."


class ProviderRateLimitError(FlightProviderError):
    safe_message = "Check failed · provider rate limit reached."


class ProviderResponseError(FlightProviderError):
    safe_message = "Check failed · provider returned an unusable response."


@dataclass(frozen=True)
class FlightSearchRequest:
    outbound_origin: str
    outbound_destination: str
    outbound_date: str
    return_origin: str
    return_destination: str
    return_date: str
    adults: int
    cabin_class: str
    currency: str


@dataclass(frozen=True)
class NormalizedOffer:
    total_price_cents: int
    currency: str
    outbound_duration_minutes: int
    return_duration_minutes: int
    outbound_stops: int
    return_stops: int
    airline_summary: str
    itinerary_summary: str
    provider_offer_reference: str
    booking_url: str
    fingerprint: str


class FlightProvider(Protocol):
    name: str

    def is_configured(self) -> bool: ...
    def search(self, request: FlightSearchRequest) -> list[NormalizedOffer]: ...


def request_from_tracker(tracker: FlightTracker) -> FlightSearchRequest:
    """Expose only the fields required for a flight-price search."""
    return FlightSearchRequest(
        outbound_origin=tracker.outbound_origin, outbound_destination=tracker.outbound_destination,
        outbound_date=tracker.outbound_date.isoformat(), return_origin=tracker.return_origin,
        return_destination=tracker.return_destination, return_date=tracker.return_date.isoformat(),
        adults=tracker.adults, cabin_class=tracker.cabin_class, currency=tracker.currency,
    )


class AmadeusFlightProvider:
    """Official REST adapter; it is dormant until local credentials are supplied."""

    name = "amadeus"
    token_url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    search_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"

    def __init__(self, client_id: str, client_secret: str, timeout_seconds: int = 15):
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _json(self, request: Request) -> dict:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # nosec B310: fixed HTTPS endpoints
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code in {401, 403}:
                raise ProviderAuthenticationError from error
            if error.code == 429:
                raise ProviderRateLimitError from error
            raise FlightProviderError from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise FlightProviderError from error

    def _token(self) -> str:
        body = urlencode({"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret}).encode()
        payload = self._json(Request(self.token_url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST"))
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise ProviderAuthenticationError
        return token

    def search(self, search: FlightSearchRequest) -> list[NormalizedOffer]:
        if not self.is_configured():
            raise ProviderNotConfigured
        # This endpoint searches a conventional return itinerary. Do not silently
        # substitute an open-jaw return route with the outbound route.
        if (
            search.return_origin != search.outbound_destination
            or search.return_destination != search.outbound_origin
        ):
            error = ProviderResponseError()
            error.safe_message = "This provider setup does not support open-jaw searches yet."
            raise error
        query = urlencode({
            "originLocationCode": search.outbound_origin, "destinationLocationCode": search.outbound_destination,
            "departureDate": search.outbound_date, "returnDate": search.return_date, "adults": search.adults,
            "travelClass": search.cabin_class.upper(), "currencyCode": search.currency, "max": 20,
        })
        token = self._token()
        payload = self._json(Request(f"{self.search_url}?{query}", headers={"Authorization": f"Bearer {token}"}))
        return normalize_amadeus_offers(payload)


def _iso_duration_minutes(value: str) -> int:
    match = re.fullmatch(r"P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?", value or "")
    if not match:
        raise ProviderResponseError
    return int(match.group(1) or 0) * 60 + int(match.group(2) or 0)


def _price_cents(value) -> int:
    try:
        cents = int((Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100))
    except (InvalidOperation, ValueError):
        raise ProviderResponseError from None
    if cents <= 0:
        raise ProviderResponseError
    return cents


def _safe_booking_url(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.netloc and len(value) <= 1000 else ""


def _fingerprint(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def normalize_amadeus_offers(payload: dict) -> list[NormalizedOffer]:
    """Convert documented Amadeus offer shapes into the app's minimal model."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ProviderResponseError
    carriers = payload.get("dictionaries", {}).get("carriers", {})
    normalized: list[NormalizedOffer] = []
    for raw in payload["data"]:
        try:
            itineraries = raw["itineraries"]
            if not isinstance(itineraries, list) or len(itineraries) != 2:
                continue
            segments = [itinerary.get("segments", []) for itinerary in itineraries]
            if not all(isinstance(item, list) and item for item in segments):
                continue
            durations = [_iso_duration_minutes(item["duration"]) for item in itineraries]
            stops = [max(len(item) - 1, 0) for item in segments]
            carrier_codes = []
            segment_marks = []
            for itinerary in segments:
                for segment in itinerary:
                    code = segment.get("carrierCode", "")
                    carrier_codes.append(code)
                    segment_marks.append(f"{code}{segment.get('number', '')}")
            airline_names = list(dict.fromkeys(str(carriers.get(code, code)) for code in carrier_codes if code))
            price = raw["price"]
            cents, currency = _price_cents(price["grandTotal"]), str(price["currency"])
            if not re.fullmatch(r"[A-Z]{3}", currency):
                continue
            reference = str(raw.get("id", ""))[:160]
            booking_url = _safe_booking_url(raw.get("bookingUrl"))
            fingerprint = _fingerprint([currency, str(cents), str(durations[0]), str(durations[1]), str(stops[0]), str(stops[1]), *segment_marks])
            normalized.append(NormalizedOffer(
                total_price_cents=cents, currency=currency, outbound_duration_minutes=durations[0], return_duration_minutes=durations[1],
                outbound_stops=stops[0], return_stops=stops[1], airline_summary=" / ".join(airline_names)[:240],
                itinerary_summary="Round trip via " + " / ".join(airline_names)[:450], provider_offer_reference=reference,
                booking_url=booking_url, fingerprint=fingerprint,
            ))
        except (KeyError, TypeError, ProviderResponseError):
            continue
    return normalized


def configured_provider() -> FlightProvider:
    override = current_app.extensions.get("flight_provider")
    if override is not None:
        return override
    if current_app.config.get("FLIGHT_PROVIDER", "").strip().lower() == "amadeus":
        return AmadeusFlightProvider(current_app.config.get("AMADEUS_CLIENT_ID", ""), current_app.config.get("AMADEUS_CLIENT_SECRET", ""))
    return AmadeusFlightProvider("", "")


def classify_offer(tracker: FlightTracker, offer: NormalizedOffer) -> str | None:
    passes = (
        offer.outbound_duration_minutes <= tracker.primary_max_duration_minutes
        and offer.return_duration_minutes <= tracker.primary_max_duration_minutes
        and offer.outbound_stops <= tracker.primary_max_stops
        and offer.return_stops <= tracker.primary_max_stops
    )
    if passes:
        return "primary"
    return "secondary" if tracker.secondary_enabled else None


class FlightSearchService:
    def __init__(self, provider: FlightProvider | None = None):
        self.provider = provider or configured_provider()

    def is_configured(self) -> bool:
        return self.provider.is_configured()

    def check(self, tracker: FlightTracker) -> AutomationRun:
        if tracker.automation.status != "active":
            raise ValueError("Only active trackers can be checked.")
        if not self.is_configured():
            raise ProviderNotConfigured
        running = db.session.scalar(db.select(AutomationRun.id).where(AutomationRun.automation_id == tracker.automation_id, AutomationRun.status == "running"))
        if running:
            raise ValueError("A flight check is already in progress.")
        run = AutomationRun(automation=tracker.automation, status="running", provider=self.provider.name, configuration_version=tracker.configuration_version)
        db.session.add(run); db.session.flush()
        try:
            offers = self.provider.search(request_from_tracker(tracker))
            seen: set[str] = set(); saved = []
            for category in ("primary", "secondary"):
                category_offers = sorted((offer for offer in offers if classify_offer(tracker, offer) == category), key=lambda offer: offer.total_price_cents)
                for offer in category_offers:
                    if offer.fingerprint in seen:
                        continue
                    seen.add(offer.fingerprint)
                    saved.append(FlightOffer(run=run, tracker=tracker, configuration_version=tracker.configuration_version, category=category, total_price_cents=offer.total_price_cents, currency=offer.currency, outbound_duration_minutes=offer.outbound_duration_minutes, return_duration_minutes=offer.return_duration_minutes, outbound_stops=offer.outbound_stops, return_stops=offer.return_stops, airline_summary=offer.airline_summary, itinerary_summary=offer.itinerary_summary, provider_offer_reference=offer.provider_offer_reference, booking_url=offer.booking_url, fingerprint=offer.fingerprint))
                    if sum(item.category == category for item in saved) >= 5:
                        break
            db.session.add_all(saved)
            run.status = "succeeded"; run.finished_at = utc_now(); run.summary = f"{len(saved)} offers saved" if saved else "No matching offers returned"
            tracker.automation.last_checked_at = utc_now()
            db.session.commit()
        except FlightProviderError as error:
            run.status = "failed"; run.finished_at = utc_now(); run.summary = error.safe_message
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return run
