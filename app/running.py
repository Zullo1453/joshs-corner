"""Decimal-safe running records, route identity, and derived progress."""
from datetime import date, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import unicodedata

from flask import current_app
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from .extensions import db
from .models import Run, RunRoute

DISTANCE_WINDOWS = {1: (Decimal("0.98"), Decimal("1.02")),
                    5: (Decimal("4.95"), Decimal("5.05")),
                    10: (Decimal("9.90"), Decimal("10.10"))}


def local_today():
    return current_app.config.get("EXERCISE_TODAY") or date.today()


def route_name(value):
    name = " ".join((value or "").split())
    key = unicodedata.normalize("NFKC", name).casefold()
    if not name or len(name) > 160 or len(key) > 320:
        raise ValueError("Enter a route name up to 160 characters.")
    return name, key


def parse_duration(value):
    parts = (value or "").strip().split(":")
    if len(parts) not in (2, 3) or any(not re.fullmatch(r"[0-9]{1,4}", item) for item in parts):
        raise ValueError("Use m:ss or h:mm:ss for elapsed time.")
    values = [int(item) for item in parts]
    if values[-1] >= 60 or (len(values) == 3 and values[-2] >= 60):
        raise ValueError("Seconds and the minutes in h:mm:ss must be below 60.")
    seconds = values[-2] * 60 + values[-1] + (values[0] * 3600 if len(values) == 3 else 0)
    if not 0 < seconds <= 604800:
        raise ValueError("Elapsed time must be positive and no more than seven days.")
    return seconds


def format_duration(value):
    seconds = int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def parse_distance(value):
    try:
        distance = Decimal((value or "").strip())
    except InvalidOperation:
        raise ValueError("Enter a valid distance in kilometres.") from None
    if not distance.is_finite() or not Decimal("0.001") <= distance <= 1000:
        raise ValueError("Distance must be between 0.001 and 1,000 km.")
    if distance != distance.quantize(Decimal("0.001")):
        raise ValueError("Use no more than three decimal places for distance.")
    return distance


def pace(run):
    return Decimal(run.elapsed_seconds) / run.distance_km


def format_pace(value):
    return format_duration(value) + " /km"


def format_distance(value):
    return f"{Decimal(str(value)):.3f}".rstrip("0").rstrip(".")


def all_runs(route_id=None):
    statement = select(Run).options(joinedload(Run.route))
    if route_id is not None:
        statement = statement.where(Run.route_id == route_id)
    return list(db.session.scalars(statement.order_by(Run.run_date.desc(), Run.run_time.desc(), Run.id.desc())))


def run_key(run):
    return run.run_date, run.run_time or time.min, run.id or 0


def run_summary(runs, today=None):
    today = today or local_today()
    monday = today - timedelta(days=today.weekday())
    longest = max(runs, key=lambda item: (item.distance_km, run_key(item)), default=None)
    fastest = min(runs, key=lambda item: (pace(item), -item.run_date.toordinal(), -(item.id or 0)), default=None)
    distance_bests = {}
    for distance, (low, high) in DISTANCE_WINDOWS.items():
        qualifying = [run for run in runs if low <= run.distance_km <= high]
        distance_bests[distance] = min(qualifying, key=lambda item: (item.elapsed_seconds, -item.run_date.toordinal(), -(item.id or 0)), default=None)
    return {
        "total": len(runs),
        "week": sum((run.distance_km for run in runs if monday <= run.run_date < monday + timedelta(days=7)), Decimal("0")),
        "month": sum((run.distance_km for run in runs if run.run_date.year == today.year and run.run_date.month == today.month), Decimal("0")),
        "longest": longest, "fastest": fastest, "distance_bests": distance_bests,
        "latest": max(runs, key=run_key, default=None),
    }


def comparable_elapsed_best(runs):
    """Compare elapsed time only when the route's whole distance range is within 1%."""
    if not runs:
        return None
    distances = [run.distance_km for run in runs]
    if max(distances) - min(distances) > min(distances) * Decimal("0.01"):
        return None
    return min(runs, key=lambda run: (run.elapsed_seconds, -run.run_date.toordinal(), -(run.id or 0)))


def run_pbs(run, runs):
    earlier = [item for item in runs if run_key(item) < run_key(run)]
    if not earlier:
        return []
    previous = run_summary(earlier, run.run_date)
    labels = []
    if run.distance_km > previous["longest"].distance_km:
        labels.append("New longest run PB")
    if pace(run) < pace(previous["fastest"]):
        labels.append("New average pace PB")
    same_route = [item for item in earlier if item.route_id == run.route_id]
    if same_route and pace(run) < min(pace(item) for item in same_route):
        labels.append("New route pace PB")
    for distance, (low, high) in DISTANCE_WINDOWS.items():
        best = previous["distance_bests"][distance]
        if low <= run.distance_km <= high and (best is None or run.elapsed_seconds < best.elapsed_seconds):
            labels.append(f"{'New' if best else 'First'} recorded {distance} km PB")
    return labels


def run_points(runs):
    return [{
        "id": run.id, "date": run.run_date.isoformat(), "route": run.route.name,
        "distance": float(run.distance_km), "pace": float(pace(run)),
        "duration": format_duration(run.elapsed_seconds), "elapsed": run.elapsed_seconds, "pace_label": format_pace(pace(run)),
    } for run in sorted(runs, key=run_key)]


def validated_run_values(form):
    try:
        day = date.fromisoformat(form.get("run_date", ""))
        start_time = time.fromisoformat(form["run_time"]) if form.get("run_time") else None
    except ValueError:
        raise ValueError("Choose a valid date and optional start time.") from None
    # Run notes are plain text, not the site's rich-text ``notes`` editor.
    notes = (form.get("run_notes", form.get("notes")) or "").strip()
    if len(notes) > 10000:
        raise ValueError("Run notes must be 10,000 characters or fewer.")
    # Validate everything before creating or looking up a route.
    values = dict(run_date=day, run_time=start_time, distance_km=parse_distance(form.get("distance_km")),
                  elapsed_seconds=parse_duration(form.get("duration")), notes=notes)
    new_name = (form.get("new_route") or "").strip()
    if new_name:
        name, key = route_name(new_name)
        route = db.session.scalar(select(RunRoute).where(RunRoute.name_key == key))
        if route is None:
            route = RunRoute(name=name, name_key=key, distance_km=values['distance_km'])
            db.session.add(route)
    else:
        try:
            route_id = int(form.get("route_id") or "")
        except ValueError:
            raise ValueError("Choose a route or enter a new route name.") from None
        route = db.session.get(RunRoute, route_id)
        if route is None:
            raise ValueError("Choose an existing route.")
    return dict(values, route=route)


def route_progress(route, runs):
    """Compare actual completion times only around a user-defined route distance."""
    comparable = sorted((run for run in runs if route.distance_km is not None and
                         abs(run.distance_km-route.distance_km) <= route.distance_km*Decimal('0.01')),key=run_key)
    first, latest = (comparable[0], comparable[-1]) if comparable else (None, None)
    best = min(comparable,key=lambda run:(run.elapsed_seconds,-run.run_date.toordinal(),-run.id),default=None)
    change = first.elapsed_seconds-latest.elapsed_seconds if len(comparable)>1 else None
    return dict(runs=comparable,first=first,latest=latest,best=best,change=change,excluded=len(runs)-len(comparable))
