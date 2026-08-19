"""Derived Upcoming event status and deterministic future/past event queries."""
from __future__ import annotations

from datetime import date, time

from sqlalchemy import select

from .extensions import db
from .models import UpcomingEvent


def status_for(event_date: date, current_day: date | None = None) -> dict[str, object] | None:
    days = (event_date - (current_day or date.today())).days
    if days < 0:
        return None
    if days == 0:
        return {"label": "Today", "days": days}
    if days == 1:
        return {"label": "Tomorrow", "days": days}
    return {"label": f"{days} days away", "days": days}


def human_date(value: date | None) -> str:
    return "" if value is None else f"{value.day} {value.strftime('%b %Y')}"


def human_time(value: time | None) -> str:
    if value is None:
        return ""
    hour = value.strftime("%I").lstrip("0") or "12"
    return f"{hour}:{value.strftime('%M %p')}"


def upcoming_events(limit: int | None = None, current_day: date | None = None) -> list[UpcomingEvent]:
    """Future/today events; timed events sort before untimed events on a shared date."""
    statement = select(UpcomingEvent).where(UpcomingEvent.event_date >= (current_day or date.today())).order_by(
        UpcomingEvent.event_date.asc(), UpcomingEvent.event_time.is_(None).asc(),
        UpcomingEvent.event_time.asc(), UpcomingEvent.created_at.asc(), UpcomingEvent.id.asc(),
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(db.session.scalars(statement))


def past_events(current_day: date | None = None) -> list[UpcomingEvent]:
    return list(db.session.scalars(
        select(UpcomingEvent).where(UpcomingEvent.event_date < (current_day or date.today())).order_by(
            UpcomingEvent.event_date.desc(), UpcomingEvent.event_time.desc(), UpcomingEvent.created_at.desc(), UpcomingEvent.id.desc()
        )
    ))
