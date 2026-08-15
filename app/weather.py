"""Small, provider-neutral weather service for explicit manual refreshes."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .extensions import db
from .models import WeatherLocation


class WeatherProviderError(RuntimeError):
    """A safe, user-facing provider failure without implementation details."""


@dataclass(frozen=True)
class LocationMatch:
    name: str
    latitude: float
    longitude: float
    timezone: str
    country_code: str
    country: str
    admin_area: str

    @property
    def label(self) -> str:
        place = ", ".join(part for part in (self.admin_area, self.country) if part)
        return f"{self.name} — {place}" if place else self.name


WEATHER_CODES = {
    0: ("Clear sky", "☀"), 1: ("Mainly clear", "☀"), 2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁"), 45: ("Fog", "≋"), 48: ("Rime fog", "≋"),
    51: ("Light drizzle", "☂"), 53: ("Drizzle", "☂"), 55: ("Dense drizzle", "☂"),
    56: ("Freezing drizzle", "☂"), 57: ("Dense freezing drizzle", "☂"),
    61: ("Slight rain", "☂"), 63: ("Rain", "☂"), 65: ("Heavy rain", "☂"),
    66: ("Freezing rain", "☂"), 67: ("Heavy freezing rain", "☂"),
    71: ("Light snow", "❄"), 73: ("Snow", "❄"), 75: ("Heavy snow", "❄"),
    77: ("Snow grains", "❄"), 80: ("Rain showers", "☂"), 81: ("Rain showers", "☂"),
    82: ("Heavy rain showers", "☂"), 85: ("Snow showers", "❄"),
    86: ("Heavy snow showers", "❄"), 95: ("Thunderstorm", "⚡"),
    96: ("Thunderstorm with hail", "⚡"), 99: ("Severe thunderstorm with hail", "⚡"),
}


def _condition(code: Any) -> tuple[str, str]:
    try:
        return WEATHER_CODES.get(int(code), ("Conditions unavailable", "•"))
    except (TypeError, ValueError):
        return "Conditions unavailable", "•"


class OpenMeteoWeatherProvider:
    """Official Open-Meteo public Forecast and Geocoding API client."""

    timeout_seconds = 10
    user_agent = "JoshsCorner/1.0 (local manual weather refresh)"

    @classmethod
    def _get_json(cls, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{endpoint}?{urlencode(params)}"
        try:
            request = Request(url, headers={"Accept": "application/json", "User-Agent": cls.user_agent})
            with urlopen(request, timeout=cls.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise WeatherProviderError("Weather temporarily unavailable. Try refreshing again later.") from error
        if not isinstance(result, dict) or result.get("error"):
            raise WeatherProviderError("Weather temporarily unavailable. Try refreshing again later.")
        return result

    def geocode(self, query: str) -> list[LocationMatch]:
        query = (query or "").strip()
        if len(query) < 2:
            return []
        payload = self._get_json(
            "https://geocoding-api.open-meteo.com/v1/search",
            {"name": query, "count": 8, "language": "en", "format": "json"},
        )
        matches = []
        for result in payload.get("results", []):
            if not isinstance(result, dict):
                continue
            try:
                matches.append(LocationMatch(
                    name=str(result["name"]).strip(), latitude=float(result["latitude"]),
                    longitude=float(result["longitude"]), timezone=str(result["timezone"]).strip(),
                    country_code=str(result.get("country_code", "")).upper()[:8],
                    country=str(result.get("country", "")).strip(), admin_area=str(result.get("admin1", "")).strip(),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return [match for match in matches if match.name and match.timezone]

    def forecast(self, location: WeatherLocation) -> dict[str, Any]:
        payload = self._get_json(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": location.latitude, "longitude": location.longitude, "timezone": location.timezone,
                "forecast_days": 7, "temperature_unit": "celsius", "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                "current": "temperature_2m,apparent_temperature,weather_code,precipitation,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max",
            },
        )
        current = payload.get("current")
        daily = payload.get("daily")
        if not isinstance(current, dict) or not isinstance(daily, dict):
            raise WeatherProviderError("Weather temporarily unavailable. Try refreshing again later.")
        condition, icon = _condition(current.get("weather_code"))
        try:
            days = []
            for index, day in enumerate(daily["time"]):
                daily_condition, daily_icon = _condition(daily["weather_code"][index])
                days.append({
                    "date": str(day), "condition": daily_condition, "icon": daily_icon,
                    "high_c": float(daily["temperature_2m_max"][index]), "low_c": float(daily["temperature_2m_min"][index]),
                    "rain_chance": int(daily["precipitation_probability_max"][index]),
                    "precipitation_mm": float(daily["precipitation_sum"][index]), "wind_kmh": float(daily["wind_speed_10m_max"][index]),
                })
            return {
                "current": {"temperature_c": float(current["temperature_2m"]), "feels_like_c": float(current["apparent_temperature"]),
                            "condition": condition, "icon": icon, "precipitation_mm": float(current["precipitation"]),
                            "wind_kmh": float(current["wind_speed_10m"])},
                "daily": days, "timezone": str(payload.get("timezone", location.timezone)),
            }
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise WeatherProviderError("Weather temporarily unavailable. Try refreshing again later.") from error


class WeatherService:
    def __init__(self, provider=None):
        self.provider = provider or OpenMeteoWeatherProvider()

    def search_locations(self, query: str) -> list[LocationMatch]:
        return self.provider.geocode(query)

    def refresh(self, location: WeatherLocation) -> dict[str, Any]:
        snapshot = self.provider.forecast(location)
        location.cached_weather_json = json.dumps(snapshot, separators=(",", ":"))
        location.last_refreshed_at = datetime.now(timezone.utc)
        db.session.commit()
        return snapshot

    @staticmethod
    def cached(location: WeatherLocation) -> dict[str, Any] | None:
        try:
            value = json.loads(location.cached_weather_json)
            return value if isinstance(value, dict) else None
        except (TypeError, json.JSONDecodeError):
            return None
