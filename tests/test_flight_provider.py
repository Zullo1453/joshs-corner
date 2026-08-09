from dataclasses import dataclass
from datetime import date

import pytest

from app.extensions import db
from app.flight_provider import (
    AmadeusFlightProvider,
    FlightSearchRequest,
    FlightSearchService,
    NormalizedOffer,
    ProviderNotConfigured,
    ProviderResponseError,
    normalize_amadeus_offers,
    request_from_tracker,
)
from app.models import Automation, FlightTracker


def tracker():
    automation = Automation(name="Fixture search", automation_type="flight_tracker")
    item = FlightTracker(
        automation=automation, outbound_origin="AAA", outbound_destination="BBB",
        outbound_date=date(2035, 5, 10), return_origin="BBB", return_destination="AAA",
        return_date=date(2035, 5, 20), target_price_cents=100000,
        primary_max_duration_minutes=900, primary_max_stops=1, secondary_enabled=True,
    )
    db.session.add(automation)
    db.session.commit()
    return item


def offer(price, fingerprint, *, duration=600, stops=1):
    return NormalizedOffer(
        total_price_cents=price, currency="AUD", outbound_duration_minutes=duration,
        return_duration_minutes=duration, outbound_stops=stops, return_stops=stops,
        airline_summary="Fixture Air", itinerary_summary="Fixture itinerary",
        provider_offer_reference=fingerprint[:8], booking_url="", fingerprint=fingerprint,
    )


@dataclass
class FixtureProvider:
    results: list[NormalizedOffer]
    configured: bool = True
    name: str = "fixture"
    calls: int = 0

    def is_configured(self):
        return self.configured

    def search(self, request):
        self.calls += 1
        assert set(request.__dataclass_fields__) == {
            "outbound_origin", "outbound_destination", "outbound_date", "return_origin",
            "return_destination", "return_date", "adults", "cabin_class", "currency",
        }
        return self.results


def test_manual_check_normalizes_saves_current_series_and_limits_results(app):
    with app.app_context():
        item = tracker()
        provider = FixtureProvider([
            offer(120000, "a" * 64), offer(110000, "a" * 64),  # duplicate is retained only once
            offer(99000, "b" * 64), offer(90000, "c" * 64, duration=950),
        ])
        run = FlightSearchService(provider).check(item)
        assert run.status == "succeeded" and run.summary == "3 offers saved"
        assert provider.calls == 1 and item.automation.last_checked_at is not None
        saved = sorted(run.offers, key=lambda value: value.total_price_cents)
        assert [value.category for value in saved] == ["secondary", "primary", "primary"]
        assert [value.total_price_cents for value in saved] == [90000, 99000, 110000]
        assert all(value.configuration_version == 1 for value in saved)


def test_no_credentials_never_calls_provider_or_creates_a_run(app):
    with app.app_context():
        item = tracker()
        provider = FixtureProvider([], configured=False)
        with pytest.raises(ProviderNotConfigured):
            FlightSearchService(provider).check(item)
        assert provider.calls == 0
        assert item.automation.runs == []


def test_unsupported_open_jaw_is_rejected_before_network_activity():
    provider = AmadeusFlightProvider("id", "secret")
    request = FlightSearchRequest(
        outbound_origin="AAA", outbound_destination="BBB", outbound_date="2035-05-10",
        return_origin="CCC", return_destination="AAA", return_date="2035-05-20",
        adults=1, cabin_class="economy", currency="AUD",
    )
    with pytest.raises(ProviderResponseError, match="open-jaw"):
        provider.search(request)


def test_amadeus_payload_is_normalized_without_booking_link():
    payload = {
        "dictionaries": {"carriers": {"FA": "Fixture Air"}},
        "data": [{"id": "offer-1", "price": {"grandTotal": "123.45", "currency": "AUD"}, "itineraries": [
            {"duration": "PT2H15M", "segments": [{"carrierCode": "FA", "number": "1"}]},
            {"duration": "PT3H", "segments": [{"carrierCode": "FA", "number": "2"}]},
        ]}],
    }
    [result] = normalize_amadeus_offers(payload)
    assert (result.total_price_cents, result.outbound_duration_minutes, result.return_duration_minutes) == (12345, 135, 180)
    assert result.booking_url == "" and result.airline_summary == "Fixture Air"
