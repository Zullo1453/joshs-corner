"""Provider-neutral flight-tracker validation and presentation helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


IATA_CODE = re.compile(r"^[A-Z]{3}$")
CABIN_CLASSES = {"economy", "premium_economy", "business", "first"}
MATERIAL_FIELDS = (
    "outbound_origin", "outbound_destination", "outbound_date",
    "return_origin", "return_destination", "return_date", "cabin_class",
)


class TrackerValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("Flight tracker validation failed")
        self.errors = errors


@dataclass(frozen=True)
class TrackerInput:
    name: str
    outbound_origin: str
    outbound_destination: str
    outbound_date: date
    return_origin: str
    return_destination: str
    return_date: date
    adults: int
    cabin_class: str
    currency: str
    target_price_cents: int
    primary_max_duration_minutes: int
    primary_max_stops: int
    secondary_enabled: bool


def parse_tracker_input(form, today: date | None = None) -> TrackerInput:
    """Validate a submitted form without touching persistence."""
    today = today or date.today()
    errors: dict[str, str] = {}

    def code(field: str) -> str:
        value = (form.get(field) or "").strip().upper()
        if not IATA_CODE.fullmatch(value):
            errors[field] = "Use a three-letter airport or metropolitan code."
        return value

    def parsed_date(field: str) -> date | None:
        raw = (form.get(field) or "").strip()
        try:
            value = date.fromisoformat(raw)
        except ValueError:
            errors[field] = "Enter a valid date."
            return None
        if value < today:
            errors[field] = "Choose today or a future date."
        return value

    def integer(field: str, label: str, minimum: int, maximum: int) -> int | None:
        try:
            value = int((form.get(field) or "").strip())
        except ValueError:
            errors[field] = f"Enter a whole-number {label}."
            return None
        if not minimum <= value <= maximum:
            errors[field] = f"Choose a {label} between {minimum} and {maximum}."
        return value

    name = (form.get("name") or "").strip()
    if not name:
        errors["name"] = "Give this tracker a name."
    elif len(name) > 200:
        errors["name"] = "Keep the name to 200 characters or fewer."
    outbound_origin, outbound_destination = code("outbound_origin"), code("outbound_destination")
    return_origin, return_destination = code("return_origin"), code("return_destination")
    if outbound_origin and outbound_origin == outbound_destination:
        errors["outbound_destination"] = "Outbound origin and destination must differ."
    if return_origin and return_origin == return_destination:
        errors["return_destination"] = "Return origin and destination must differ."
    outbound_date, return_date = parsed_date("outbound_date"), parsed_date("return_date")
    if outbound_date and return_date and return_date < outbound_date:
        errors["return_date"] = "Return date cannot be before the outbound date."
    adults = integer("adults", "adult count", 1, 9)
    duration_hours = integer("primary_max_duration_hours", "maximum journey duration", 1, 168)
    stops = integer("primary_max_stops", "maximum stop count", 0, 6)
    cabin_class = (form.get("cabin_class") or "economy").strip().lower()
    if cabin_class not in CABIN_CLASSES:
        errors["cabin_class"] = "Choose a supported cabin class."
    currency = (form.get("currency") or "AUD").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        errors["currency"] = "Use a three-letter currency code."
    raw_price = (form.get("target_price") or "").strip().replace(",", "")
    try:
        cents = int((Decimal(raw_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100))
        if cents <= 0 or cents > 100_000_000:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        errors["target_price"] = "Enter a positive target price."
        cents = 0
    if errors:
        raise TrackerValidationError(errors)
    return TrackerInput(
        name=name, outbound_origin=outbound_origin, outbound_destination=outbound_destination,
        outbound_date=outbound_date, return_origin=return_origin, return_destination=return_destination,
        return_date=return_date, adults=adults, cabin_class=cabin_class, currency=currency,
        target_price_cents=cents, primary_max_duration_minutes=duration_hours * 60,
        primary_max_stops=stops, secondary_enabled=form.get("secondary_enabled") == "on",
    )


def tracker_form_values(tracker=None, submitted=None) -> dict[str, str | bool]:
    if submitted is not None:
        values = {key: submitted.get(key, "") for key in submitted.keys()}
        values["secondary_enabled"] = submitted.get("secondary_enabled") == "on"
        return values
    if tracker is None:
        return {"adults": "1", "cabin_class": "economy", "currency": "AUD", "secondary_enabled": True}
    return {
        "name": tracker.automation.name, "outbound_origin": tracker.outbound_origin,
        "outbound_destination": tracker.outbound_destination, "outbound_date": tracker.outbound_date.isoformat(),
        "return_origin": tracker.return_origin, "return_destination": tracker.return_destination,
        "return_date": tracker.return_date.isoformat(), "adults": str(tracker.adults),
        "cabin_class": tracker.cabin_class, "currency": tracker.currency,
        "target_price": f"{tracker.target_price_cents / 100:.2f}",
        "primary_max_duration_hours": str(tracker.primary_max_duration_minutes // 60),
        "primary_max_stops": str(tracker.primary_max_stops), "secondary_enabled": tracker.secondary_enabled,
    }


def apply_tracker_input(tracker, values: TrackerInput) -> bool:
    """Apply changes and return whether a new comparable search series begins."""
    is_new = tracker.id is None and tracker.configuration_version is None
    material_change = (not is_new) and any(
        getattr(tracker, field) != getattr(values, field) for field in MATERIAL_FIELDS
    )
    tracker.automation.name = values.name
    for field in (
        "outbound_origin", "outbound_destination", "outbound_date", "return_origin", "return_destination",
        "return_date", "adults", "cabin_class", "currency", "target_price_cents",
        "primary_max_duration_minutes", "primary_max_stops", "secondary_enabled",
    ):
        setattr(tracker, field, getattr(values, field))
    if material_change:
        tracker.configuration_version += 1
    elif is_new:
        tracker.configuration_version = 1
    return material_change


def format_duration(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    return f"{hours}h" if remainder == 0 else f"{hours}h {remainder}m"
