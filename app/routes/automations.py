from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from ..currency import CurrencyProviderError, CurrencyService, convert
from ..extensions import db
from ..health import collect_health
from ..models import CurrencyPair, WeatherLocation
from ..ordering import active_items, move_active_item, next_sort_order, normalize_active_items
from ..usage import UsageService
from ..weather import LocationMatch, WeatherProviderError, WeatherService


automations_bp = Blueprint("automations", __name__, url_prefix="/automations")


def _weather_service():
    return WeatherService(current_app.extensions.get("weather_provider"))


def _currency_service():
    return CurrencyService(current_app.extensions.get("currency_provider"))


def _saved_weather():
    service = _weather_service()
    locations = active_items(WeatherLocation, WeatherLocation.display_name)
    return [(location, service.cached(location)) for location in locations]


def _saved_currency():
    service = _currency_service()
    pairs = active_items(CurrencyPair, CurrencyPair.base_currency, CurrencyPair.quote_currency)
    return [(pair, service.cached(pair)) for pair in pairs]


@automations_bp.get("")
def overview():
    return render_template("automations/index.html", automation_page="overview", weather=_saved_weather(), currency=_saved_currency(), health=collect_health(current_app))


@automations_bp.route("/weather", methods=["GET", "POST"])
def weather():
    matches, query = [], ""
    if request.method == "POST":
        query = request.form.get("location_query", "").strip()
        try:
            matches = _weather_service().search_locations(query)
            if query and not matches:
                flash("No matching locations found. Try a city or region name.", "error")
        except WeatherProviderError as error:
            flash(str(error), "error")
    return render_template("automations/weather.html", automation_page="weather", weather=_saved_weather(), matches=matches, location_query=query)


@automations_bp.post("/weather/locations")
def add_weather_location():
    try:
        match = LocationMatch(name=request.form["name"].strip()[:200], latitude=float(request.form["latitude"]), longitude=float(request.form["longitude"]), timezone=request.form["timezone"].strip()[:64], country_code=request.form.get("country_code", "").strip().upper()[:8], country=request.form.get("country", "").strip()[:120], admin_area=request.form.get("admin_area", "").strip()[:120])
        if not match.name or not match.timezone or not -90 <= match.latitude <= 90 or not -180 <= match.longitude <= 180:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        flash("Choose a valid location from the search results.", "error")
        return redirect(url_for("automations.weather"))
    duplicate = db.session.scalar(select(WeatherLocation).where(WeatherLocation.display_name == match.name, WeatherLocation.latitude == match.latitude, WeatherLocation.longitude == match.longitude))
    if duplicate:
        duplicate.active = True
        db.session.commit()
        flash("That location is already saved.", "info")
    else:
        db.session.add(WeatherLocation(display_name=match.name, latitude=match.latitude, longitude=match.longitude, timezone=match.timezone, country_code=match.country_code, admin_area=match.admin_area, sort_order=next_sort_order(WeatherLocation)))
        db.session.commit()
        flash(f"{match.name} saved. Use Refresh to fetch the forecast.", "success")
    return redirect(url_for("automations.weather"))


@automations_bp.post("/weather/refresh")
def refresh_weather():
    locations, service, refreshed, failed = db.session.scalars(select(WeatherLocation).where(WeatherLocation.active)).all(), _weather_service(), 0, False
    for location in locations:
        try:
            service.refresh(location)
            refreshed += 1
        except WeatherProviderError:
            db.session.rollback()
            failed = True
    if refreshed:
        flash(f"Updated {refreshed} saved location{'s' if refreshed != 1 else ''}.", "success")
    if failed:
        flash("Weather temporarily unavailable for one or more locations. Saved results were kept.", "error")
    return redirect(url_for("automations.weather"))


@automations_bp.post("/weather/<int:location_id>/deactivate")
def deactivate_weather(location_id):
    location = db.get_or_404(WeatherLocation, location_id)
    location.active = False
    normalize_active_items(WeatherLocation, WeatherLocation.display_name)
    db.session.commit()
    flash("Location removed from Weather.", "info")
    return redirect(url_for("automations.weather"))


@automations_bp.post("/weather/<int:location_id>/move")
def move_weather(location_id):
    try:
        moved = move_active_item(WeatherLocation, location_id, request.form.get("action", ""), WeatherLocation.display_name)
    except ValueError:
        abort(400)
    except LookupError:
        abort(404)
    if moved:
        flash("Location order updated.", "success")
    return redirect(url_for("automations.weather"))


@automations_bp.get("/currency")
def currency():
    amount, selected_id, conversion = request.args.get("amount", ""), request.args.get("pair", type=int), None
    currency = _saved_currency()
    if selected_id and amount:
        selected = next(((pair, snapshot) for pair, snapshot in currency if pair.id == selected_id), None)
        if selected and selected[1]:
            conversion = convert(amount, selected[1]["latest"])
            if conversion is None:
                flash("Enter a valid non-negative amount.", "error")
    return render_template("automations/currency.html", automation_page="currency", currency=currency, amount=amount, selected_id=selected_id, conversion=conversion)


@automations_bp.post("/currency/pairs")
def add_currency_pair():
    base, quote = request.form.get("base_currency", "").strip().upper(), request.form.get("quote_currency", "").strip().upper()
    if len(base) != 3 or len(quote) != 3 or not base.isalpha() or not quote.isalpha():
        flash("Use three-letter currency codes, such as AUD and EUR.", "error")
    elif base == quote:
        flash("Choose two different currencies.", "error")
    else:
        existing = db.session.scalar(select(CurrencyPair).where(CurrencyPair.base_currency == base, CurrencyPair.quote_currency == quote))
        if existing:
            existing.active = True
            db.session.commit()
            flash("That currency pair is already saved.", "info")
        else:
            db.session.add(CurrencyPair(base_currency=base, quote_currency=quote, sort_order=next_sort_order(CurrencyPair)))
            db.session.commit()
            flash(f"{base} → {quote} saved. Use Refresh to fetch reference rates.", "success")
    return redirect(url_for("automations.currency"))


@automations_bp.post("/currency/refresh")
def refresh_currency():
    pairs, service, refreshed, failed = db.session.scalars(select(CurrencyPair).where(CurrencyPair.active)).all(), _currency_service(), 0, False
    for pair in pairs:
        try:
            service.refresh(pair)
            refreshed += 1
        except CurrencyProviderError:
            db.session.rollback()
            failed = True
    if refreshed:
        flash(f"Updated {refreshed} saved pair{'s' if refreshed != 1 else ''}.", "success")
    if failed:
        flash("Currency rates are temporarily unavailable for one or more pairs. Saved results were kept.", "error")
    return redirect(url_for("automations.currency"))


@automations_bp.post("/currency/<int:pair_id>/deactivate")
def deactivate_currency(pair_id):
    pair = db.get_or_404(CurrencyPair, pair_id)
    pair.active = False
    normalize_active_items(CurrencyPair, CurrencyPair.base_currency, CurrencyPair.quote_currency)
    db.session.commit()
    flash("Currency pair removed from Currency.", "info")
    return redirect(url_for("automations.currency"))


@automations_bp.post("/currency/<int:pair_id>/move")
def move_currency(pair_id):
    try:
        moved = move_active_item(CurrencyPair, pair_id, request.form.get("action", ""), CurrencyPair.base_currency, CurrencyPair.quote_currency)
    except ValueError:
        abort(400)
    except LookupError:
        abort(404)
    if moved:
        flash("Currency pair order updated.", "success")
    return redirect(url_for("automations.currency"))


@automations_bp.route("/health", methods=["GET", "POST"])
def health():
    return render_template("automations/health.html", automation_page="health", health=collect_health(current_app), checked=request.method == "POST")


@automations_bp.get("/usage")
def usage():
    service = UsageService(current_app)
    return render_template("automations/usage.html", automation_page="usage", usage=service.local_usage(), counts=service.database_counts())


@automations_bp.get("/trackers")
@automations_bp.get("/alerts")
@automations_bp.get("/history")
def legacy_routes():
    return redirect(url_for("automations.overview"), code=302)
