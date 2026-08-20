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

    def history(
        self,
        base: str,
        quote: str,
        days: int = 30,
        *,
        group: str | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, str]]:
        end = end_date or date.today()
        params = {"base": base, "quotes": quote, "from": (end - timedelta(days=days)).isoformat(), "to": end.isoformat()}
        if group:
            params["group"] = group
        payload = self._get_json("https://api.frankfurter.dev/v2/rates", params)
        if not isinstance(payload, list):
            raise CurrencyProviderError("Currency rates are temporarily unavailable. Try refreshing again later.")
        points_by_date = {}
        try:
            for item in payload:
                if item.get("base") == base and item.get("quote") == quote:
                    rate = Decimal(str(item["rate"]))
                    if rate > 0:
                        point_date = date.fromisoformat(str(item["date"])).isoformat()
                        points_by_date[point_date] = {"date": point_date, "rate": format(rate, "f")}
        except (AttributeError, InvalidOperation, KeyError, TypeError, ValueError) as error:
            raise CurrencyProviderError("Currency rates are temporarily unavailable. Try refreshing again later.") from error
        points = sorted(points_by_date.values(), key=lambda point: point["date"])
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
        metric_points = self.provider.history(pair.base_currency, pair.quote_currency, 30)
        latest_date = date.fromisoformat(metric_points[-1]["date"])
        chart_points = self.provider.history(
            pair.base_currency,
            pair.quote_currency,
            365,
            group="week",
            end_date=latest_date,
        )
        snapshot = {"points": metric_points, "chart_points": chart_points}
        pair.cached_rates_json = json.dumps(snapshot, separators=(",", ":"))
        pair.last_refreshed_at = datetime.now(timezone.utc)
        db.session.commit()
        return self._snapshot(metric_points, chart_points)

    @staticmethod
    def _snapshot(metric_points: list[dict[str, str]], chart_points: list[dict[str, str]]) -> dict[str, Any]:
        snapshot = calculate_metrics(metric_points)
        snapshot["chart_points"] = chart_points
        chart_start = date.fromisoformat(chart_points[0]["date"])
        chart_end = date.fromisoformat(chart_points[-1]["date"])
        snapshot["chart_period_label"] = "Past 12 months" if chart_end - chart_start >= timedelta(days=300) else "Recent history"
        return snapshot

    @staticmethod
    def cached(pair: CurrencyPair) -> dict[str, Any] | None:
        try:
            payload = json.loads(pair.cached_rates_json)
            metric_points = payload.get("points") if isinstance(payload, dict) else None
            chart_points = (payload.get("chart_points") or metric_points) if isinstance(payload, dict) else metric_points
            if not isinstance(metric_points, list) or not metric_points or not isinstance(chart_points, list) or not chart_points:
                return None
            return CurrencyService._snapshot(metric_points, chart_points)
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
