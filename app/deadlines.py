"""Derived calendar-day deadline status and shared active-deadline queries."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from .extensions import db
from .models import Deadline


def status_for(due_date: date, current_day: date | None = None) -> dict[str, object]:
    """Return an injectable, date-only status; no timestamp-hour arithmetic is used."""
    days = (due_date - (current_day or date.today())).days
    if days < 0:
        amount = abs(days)
        return {"label": f"{amount} day{'s' if amount != 1 else ''} overdue", "tone": "overdue", "days": days}
    if days == 0:
        return {"label": "Due today", "tone": "today", "days": days}
    return {"label": f"{days} day{'s' if days != 1 else ''} left", "tone": "soon" if days <= 3 else "normal", "days": days}


def human_date(value: date | None) -> str:
    return "" if value is None else f"{value.day} {value.strftime('%b %Y')}"


def active_deadlines(limit: int | None = None) -> list[Deadline]:
    statement = select(Deadline).where(~Deadline.is_completed).order_by(
        Deadline.due_date.asc(), Deadline.created_at.asc(), Deadline.id.asc()
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(db.session.scalars(statement))
