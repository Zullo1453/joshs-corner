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


def _weather_names(app):
    with app.app_context():
        return [item.display_name for item in db.session.scalars(db.select(WeatherLocation).where(WeatherLocation.active).order_by(WeatherLocation.sort_order, WeatherLocation.display_name))]


def _currency_names(app):
    with app.app_context():
        return [f"{item.base_currency}/{item.quote_currency}" for item in db.session.scalars(db.select(CurrencyPair).where(CurrencyPair.active).order_by(CurrencyPair.sort_order, CurrencyPair.base_currency, CurrencyPair.quote_currency))]


def test_order_controls_submit_once_without_global_shift_window_behaviour():
    script = (Path(__file__).parents[1] / "app" / "static" / "js" / "order_controls.js").read_text(encoding="utf-8")
    assert 'event.preventDefault()' in script
    assert 'event.stopImmediatePropagation()' in script
    assert 'button.form?.requestSubmit(button)' in script
    assert 'event.shiftKey' in script and 'data-shift-action' in script
    assert 'window.open' not in script


def test_weather_ordering_moves_one_step_or_to_boundary_and_preserves_cached_data(app, client):
    with app.app_context():
        cached_c = '{"current":{"icon":"☀","temperature_c":20,"condition":"Clear","feels_like_c":20,"precipitation_mm":0,"wind_kmh":0},"daily":[],"timezone":"UTC"}'
        locations = [WeatherLocation(display_name=name, latitude=index, longitude=index, timezone="UTC", sort_order=index, cached_weather_json=cached_c if name == "C" else None) for index, name in enumerate(("A", "B", "C", "D"))]
        db.session.add_all(locations)
        db.session.commit()
        ids = {item.display_name: item.id for item in locations}
    assert client.post(f"/automations/weather/{ids['C']}/move", data={"action": "up"}).status_code == 302
    assert _weather_names(app) == ["A", "C", "B", "D"]
    assert client.post(f"/automations/weather/{ids['C']}/move", data={"action": "down"}).status_code == 302
    assert _weather_names(app) == ["A", "B", "C", "D"]
    client.post(f"/automations/weather/{ids['D']}/move", data={"action": "top"})
    assert _weather_names(app) == ["D", "A", "B", "C"]
    client.post(f"/automations/weather/{ids['D']}/move", data={"action": "bottom"})
    assert _weather_names(app) == ["A", "B", "C", "D"]
    client.post("/automations/weather/locations", data={"name": "E", "latitude": "10", "longitude": "10", "timezone": "UTC"})
    assert _weather_names(app) == ["A", "B", "C", "D", "E"]
    client.post(f"/automations/weather/{ids['B']}/deactivate")
    assert _weather_names(app) == ["A", "C", "D", "E"]
    response = client.get("/automations/weather")
    assert b'Move A up' in response.data and b'disabled' in response.data and b'Move D down' in response.data
    assert client.post(f"/automations/weather/{ids['A']}/move", data={"action": "sideways"}).status_code == 400
    assert client.post("/automations/weather/99999/move", data={"action": "up"}).status_code == 404
    with app.app_context():
        assert db.session.get(WeatherLocation, ids["C"]).cached_weather_json == cached_c
        assert [item.sort_order for item in db.session.scalars(db.select(WeatherLocation).where(WeatherLocation.active).order_by(WeatherLocation.sort_order))] == [0, 1, 2, 3]


def test_currency_ordering_persists_and_does_not_mix_rate_caches(app, client):
    with app.app_context():
        pairs = [CurrencyPair(base_currency="AUD", quote_currency=quote, sort_order=index, cached_rates_json=f'{{"pair":"{quote}"}}') for index, quote in enumerate(("EUR", "CZK", "USD", "GBP"))]
        db.session.add_all(pairs)
        db.session.commit()
        ids = {item.quote_currency: item.id for item in pairs}
    client.post(f"/automations/currency/{ids['USD']}/move", data={"action": "up"})
    assert _currency_names(app) == ["AUD/EUR", "AUD/USD", "AUD/CZK", "AUD/GBP"]
    client.post(f"/automations/currency/{ids['USD']}/move", data={"action": "down"})
    client.post(f"/automations/currency/{ids['GBP']}/move", data={"action": "top"})
    assert _currency_names(app) == ["AUD/GBP", "AUD/EUR", "AUD/CZK", "AUD/USD"]
    client.post(f"/automations/currency/{ids['GBP']}/move", data={"action": "bottom"})
    assert _currency_names(app) == ["AUD/EUR", "AUD/CZK", "AUD/USD", "AUD/GBP"]
    client.post("/automations/currency/pairs", data={"base_currency": "AUD", "quote_currency": "JPY"})
    assert _currency_names(app) == ["AUD/EUR", "AUD/CZK", "AUD/USD", "AUD/GBP", "AUD/JPY"]
    client.post(f"/automations/currency/{ids['CZK']}/deactivate")
    assert _currency_names(app) == ["AUD/EUR", "AUD/USD", "AUD/GBP", "AUD/JPY"]
    response = client.get("/automations/currency")
    assert b'Move AUD to EUR up' in response.data and b'pair-arrow' in response.data
    assert client.post(f"/automations/currency/{ids['EUR']}/move", data={"action": "invalid"}).status_code == 400
    with app.app_context():
        assert db.session.get(CurrencyPair, ids["CZK"]).cached_rates_json == '{"pair":"CZK"}'
        assert [item.sort_order for item in db.session.scalars(db.select(CurrencyPair).where(CurrencyPair.active).order_by(CurrencyPair.sort_order))] == [0, 1, 2, 3]


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
