from datetime import date, timedelta
from decimal import Decimal

from app.currency import CurrencyProviderError, CurrencyService, calculate_metrics, convert
from app.extensions import db
from app.models import CurrencyPair, WeatherLocation
from app.weather import LocationMatch, WeatherProviderError, WeatherService
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text
from pathlib import Path
from app import create_app


class WeatherProvider:
    def geocode(self, query):
        return [LocationMatch("Test City", 1.2, 3.4, "UTC", "TC", "Testland", "Region")] if query == "Test City" else []

    def forecast(self, location):
        return {"current": {"temperature_c": 21, "feels_like_c": 20, "condition": "Partly cloudy", "icon": "⛅", "precipitation_mm": 1.8, "wind_kmh": 18}, "daily": [{"date": f"2026-08-{day:02d}", "condition": "Clear sky", "icon": "☀", "high_c": 24, "low_c": 16, "rain_chance": 35, "precipitation_mm": 1.8, "wind_kmh": 18} for day in range(1, 8)], "timezone": "UTC"}


class OfflineWeatherProvider(WeatherProvider):
    def forecast(self, location):
        raise WeatherProviderError("Weather temporarily unavailable. Try refreshing again later.")


class CurrencyProvider:
    def history(self, base, quote, days):
        return [{"date": (date(2026, 8, 1) + timedelta(days=index)).isoformat(), "rate": str(Decimal("0.50") + Decimal(index) / 100)} for index in range(31)]


class OfflineCurrencyProvider(CurrencyProvider):
    def history(self, base, quote, days):
        raise CurrencyProviderError("Currency rates are temporarily unavailable. Try refreshing again later.")


def test_weather_search_add_refresh_and_failure_retains_cached_result(app, client):
    app.extensions["weather_provider"] = WeatherProvider()
    response = client.post("/automations/weather", data={"location_query": "Test City"})
    assert b"Test City" in response.data and b"Region" in response.data
    response = client.post("/automations/weather/locations", data={"name": "Test City", "latitude": "1.2", "longitude": "3.4", "timezone": "UTC", "country_code": "TC", "country": "Testland", "admin_area": "Region"})
    assert response.status_code == 302
    response = client.post("/automations/weather/refresh", follow_redirects=True)
    assert b"21" in response.data and b"7-day" not in response.data
    with app.app_context():
        location = db.session.scalar(db.select(WeatherLocation))
        cached = location.cached_weather_json
        assert location.last_refreshed_at is not None
    app.extensions["weather_provider"] = OfflineWeatherProvider()
    response = client.post("/automations/weather/refresh", follow_redirects=True)
    assert b"Saved results were kept" in response.data
    with app.app_context():
        assert db.session.scalar(db.select(WeatherLocation)).cached_weather_json == cached


def test_currency_normalizes_adds_refreshes_and_uses_decimal_converter(app, client):
    app.extensions["currency_provider"] = CurrencyProvider()
    response = client.post("/automations/currency/pairs", data={"base_currency": "aud", "quote_currency": "eur"})
    assert response.status_code == 302
    response = client.post("/automations/currency/refresh", follow_redirects=True)
    assert b"1 AUD" in response.data and b"30-day high / low" in response.data
    with app.app_context():
        pair = db.session.scalar(db.select(CurrencyPair))
        assert (pair.base_currency, pair.quote_currency) == ("AUD", "EUR")
        pair_id = pair.id
    response = client.get(f"/automations/currency?pair={pair_id}&amount=1000")
    assert b"\xe2\x89\x88 800.00 EUR" in response.data
    assert convert("0.1", Decimal("0.2")) == Decimal("0.02")
    assert convert("-1", Decimal("1")) is None


def test_currency_validation_metrics_and_failure_retains_cache(app, client):
    assert b"three-letter currency" in client.post("/automations/currency/pairs", data={"base_currency": "AU", "quote_currency": "EUR"}, follow_redirects=True).data
    assert b"different currencies" in client.post("/automations/currency/pairs", data={"base_currency": "AUD", "quote_currency": "AUD"}, follow_redirects=True).data
    points = CurrencyProvider().history("AUD", "EUR", 30)
    metrics = calculate_metrics(points)
    assert metrics["high"] == Decimal("0.80") and metrics["low"] == Decimal("0.50") and metrics["change_30d"] == Decimal("60.0")
    app.extensions["currency_provider"] = CurrencyProvider()
    client.post("/automations/currency/pairs", data={"base_currency": "AUD", "quote_currency": "EUR"})
    client.post("/automations/currency/refresh")
    with app.app_context():
        cached = db.session.scalar(db.select(CurrencyPair)).cached_rates_json
    app.extensions["currency_provider"] = OfflineCurrencyProvider()
    assert b"Saved results were kept" in client.post("/automations/currency/refresh", follow_redirects=True).data
    with app.app_context():
        assert db.session.scalar(db.select(CurrencyPair)).cached_rates_json == cached


def test_health_is_read_only_and_hides_paths_and_secrets(app, client):
    with app.app_context():
        before = db.session.scalar(db.select(db.func.count(WeatherLocation.id)))
    response = client.post("/automations/health")
    assert response.status_code == 200
    assert b"This diagnostic does not change data" in response.data
    assert b"D:\\" not in response.data and b"SECRET_KEY" not in response.data
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(WeatherLocation.id))) == before


def test_stage3_tool_migrations_upgrade_downgrade_and_reupgrade(tmp_path):
    database = tmp_path / "stage3-tools.db"
    migration_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with migration_app.app_context():
        upgrade(directory=str(migrations), revision="9a7b3c5d8e10")
        db.session.execute(text("INSERT INTO automation (name, automation_type, status, created_at, updated_at) VALUES ('Preserved', 'future', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        db.session.commit()
        upgrade(directory=str(migrations), revision="head")
        assert {"weather_location", "currency_pair"}.issubset(inspect(db.engine).get_table_names())
        downgrade(directory=str(migrations), revision="9a7b3c5d8e10")
        assert not {"weather_location", "currency_pair"}.intersection(inspect(db.engine).get_table_names())
        assert db.session.execute(text("SELECT name FROM automation")).scalar() == "Preserved"
        upgrade(directory=str(migrations), revision="head")
        assert {"weather_location", "currency_pair"}.issubset(inspect(db.engine).get_table_names())
