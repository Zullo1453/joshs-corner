"""Lazy, local recurrence generation and aggregation for standalone To-Dos."""
from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select

from .extensions import db
from .models import RecurrenceRule, TaskOccurrence, utc_now


WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class RecurringTaskView:
    rule: RecurrenceRule
    outstanding_count: int
    oldest_due_date: date


def recurrence_dates(rule: RecurrenceRule, through: date):
    """Yield due dates from the rule start through a date, using last-day monthly fallback."""
    end = min(through, rule.end_date) if rule.end_date else through
    if end < rule.start_date:
        return
    if rule.recurrence_type == "daily":
        current = rule.start_date
        while current <= end:
            yield current
            current += timedelta(days=rule.interval)
    elif rule.recurrence_type == "weekly":
        weekdays = {int(value) for value in json.loads(rule.weekdays_json)}
        current = rule.start_date
        while current <= end:
            if current.weekday() in weekdays and ((current - rule.start_date).days // 7) % rule.interval == 0:
                yield current
            current += timedelta(days=1)
    elif rule.recurrence_type == "monthly":
        month_index = rule.start_date.year * 12 + rule.start_date.month - 1
        end_index = end.year * 12 + end.month - 1
        while month_index <= end_index:
            year, month = divmod(month_index, 12)
            month += 1
            due = date(year, month, min(rule.day_of_month, calendar.monthrange(year, month)[1]))
            if due >= rule.start_date and due <= end:
                yield due
            month_index += rule.interval


def generate_occurrences(through: date):
    """Generate every missed occurrence exactly once when the app is opened."""
    rules = db.session.execute(
        select(RecurrenceRule).where(RecurrenceRule.is_active.is_(True), RecurrenceRule.start_date <= through)
    ).scalars().all()
    for rule in rules:
        existing = set(db.session.execute(
            select(TaskOccurrence.due_date).where(TaskOccurrence.recurrence_rule_id == rule.id)
        ).scalars())
        for due_date in recurrence_dates(rule, through):
            if due_date not in existing:
                db.session.add(TaskOccurrence(recurrence_rule_id=rule.id, due_date=due_date))
    db.session.commit()


def active_recurring_tasks(today: date):
    generate_occurrences(today)
    occurrences = db.session.execute(
        select(TaskOccurrence).join(TaskOccurrence.rule).where(
            TaskOccurrence.completed_at.is_(None),
            TaskOccurrence.discarded_at.is_(None),
            TaskOccurrence.due_date <= today,
        ).order_by(TaskOccurrence.due_date.asc(), TaskOccurrence.id.asc())
    ).scalars().all()
    grouped = {}
    for occurrence in occurrences:
        rule = occurrence.rule
        if rule.rollover_enabled or occurrence.due_date == today:
            grouped.setdefault(rule.id, []).append(occurrence)
    return tuple(
        RecurringTaskView(rule=items[0].rule, outstanding_count=len(items), oldest_due_date=items[0].due_date)
        for items in grouped.values()
    )


def complete_oldest(rule_id: int):
    occurrence = db.session.execute(
        select(TaskOccurrence).where(
            TaskOccurrence.recurrence_rule_id == rule_id,
            TaskOccurrence.completed_at.is_(None),
            TaskOccurrence.discarded_at.is_(None),
        ).order_by(TaskOccurrence.due_date.asc(), TaskOccurrence.id.asc()).limit(1)
    ).scalar_one_or_none()
    if occurrence is None:
        return False
    occurrence.completed_at = utc_now()
    db.session.commit()
    return True


def discard_oldest(rule_id: int):
    occurrence = db.session.execute(
        select(TaskOccurrence).where(
            TaskOccurrence.recurrence_rule_id == rule_id,
            TaskOccurrence.completed_at.is_(None),
            TaskOccurrence.discarded_at.is_(None),
        ).order_by(TaskOccurrence.due_date.asc(), TaskOccurrence.id.asc()).limit(1)
    ).scalar_one_or_none()
    if occurrence is None:
        return False
    occurrence.discarded_at = utc_now()
    db.session.commit()
    return True


def summary(rule: RecurrenceRule):
    if rule.recurrence_type == "daily":
        return "Repeats daily" if rule.interval == 1 else f"Repeats every {rule.interval} days"
    if rule.recurrence_type == "weekly":
        days = [WEEKDAYS[index] for index in json.loads(rule.weekdays_json)]
        return "Repeats every " + " and ".join(days)
    return f"Repeats monthly on day {rule.day_of_month}"
