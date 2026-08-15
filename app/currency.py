"""Manual, cached reference-rate service backed by Frankfurter's public API."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .extensions import db
from .models import CurrencyPair


class CurrencyProviderError(RuntimeError):
    """A safe, user-facing rate provider failure."""


class FrankfurterProvider:
    timeout_seconds = 10
    user_agent = "JoshsCorner/1.0 (local manual currency refresh)"

    @classmethod
    def _get_json(cls, endpoint: str, params: dict[str, Any]) -> Any:
        try:
            request = Request(f"{endpoint}?{urlencode(params)}", headers={"Accept": "application/json", "User-Agent": cls.user_agent})
            with urlopen(request, timeout=cls.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise CurrencyProviderError("Currency rates are temporarily unavailable. Try refreshing again later.") from error

    def history(self, base: str, quote: str, days: int = 30) -> list[dict[str, str]]:
        start = (date.today() - timedelta(days=days)).isoformat()
        payload = self._get_json("https://api.frankfurter.dev/v2/rates", {"base": base, "quotes": quote, "from": start})
        if not isinstance(payload, list):
            raise CurrencyProviderError("Currency rates are temporarily unavailable. Try refreshing again later.")
        points = []
        try:
            for item in payload:
                if item.get("base") == base and item.get("quote") == quote:
                    rate = Decimal(str(item["rate"]))
                    if rate > 0:
                        points.append({"date": str(item["date"]), "rate": format(rate, "f")})
        except (AttributeError, InvalidOperation, KeyError, TypeError, ValueError) as error:
            raise CurrencyProviderError("Currency rates are temporarily unavailable. Try refreshing again later.") from error
        points.sort(key=lambda point: point["date"])
        if not points:
            raise CurrencyProviderError("No reference rate is currently available for this pair.")
        return points


def calculate_metrics(points: list[dict[str, str]]) -> dict[str, Any]:
    values = [(point["date"], Decimal(str(point["rate"]))) for point in points]
    latest_date, latest = values[-1]
    previous = values[-2][1] if len(values) > 1 else None
    def percentage(reference):
        return ((latest - reference) / reference * Decimal("100")) if reference else None
    seven_reference = next((value for day, value in reversed(values) if day <= (date.fromisoformat(latest_date) - timedelta(days=7)).isoformat()), values[0][1])
    return {
        "points": [{"date": day, "rate": format(rate, "f")} for day, rate in values], "latest": latest,
        "latest_date": latest_date, "previous": previous, "change_7d": percentage(seven_reference),
        "change_30d": percentage(values[0][1]), "high": max(value for _, value in values), "low": min(value for _, value in values),
    }


class CurrencyService:
    def __init__(self, provider=None):
        self.provider = provider or FrankfurterProvider()

    def refresh(self, pair: CurrencyPair) -> dict[str, Any]:
        points = self.provider.history(pair.base_currency, pair.quote_currency, 30)
        snapshot = {"points": points}
        pair.cached_rates_json = json.dumps(snapshot, separators=(",", ":"))
        pair.last_refreshed_at = datetime.now(timezone.utc)
        db.session.commit()
        return calculate_metrics(points)

    @staticmethod
    def cached(pair: CurrencyPair) -> dict[str, Any] | None:
        try:
            payload = json.loads(pair.cached_rates_json)
            points = payload.get("points") if isinstance(payload, dict) else None
            return calculate_metrics(points) if isinstance(points, list) and points else None
        except (TypeError, json.JSONDecodeError, KeyError, InvalidOperation, ValueError):
            return None


def convert(amount: str, rate: Decimal) -> Decimal | None:
    try:
        value = Decimal((amount or "").strip())
        if value < 0:
            return None
        return (value * rate).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
