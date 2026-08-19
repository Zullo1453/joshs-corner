from __future__ import annotations

from datetime import date, time

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import UpcomingEvent
from ..upcoming import human_date, human_time, past_events, status_for, upcoming_events


upcoming_bp = Blueprint("upcoming", __name__, url_prefix="/upcoming")


def _validated_values():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    event_date_raw = request.form.get("event_date", "").strip()
    event_time_raw = request.form.get("event_time", "").strip()
    if not title or len(title) > 200:
        raise ValueError("Enter an event title up to 200 characters.")
    if len(description) > 5000:
        raise ValueError("Description must be 5,000 characters or fewer.")
    try:
        event_date = date.fromisoformat(event_date_raw)
    except ValueError:
        raise ValueError("Choose a valid event date.") from None
    try:
        event_time = time.fromisoformat(event_time_raw) if event_time_raw else None
    except ValueError:
        raise ValueError("Choose a valid event time.") from None
    return title, description, event_date, event_time


@upcoming_bp.get("")
def index():
    return render_template(
        "upcoming/index.html", upcoming_events=upcoming_events(), past_events=past_events(),
        status_for=status_for, human_date=human_date, human_time=human_time,
    )


@upcoming_bp.post("")
def add():
    try:
        title, description, event_date, event_time = _validated_values()
    except ValueError as error:
        flash(str(error), "error")
    else:
        db.session.add(UpcomingEvent(title=title, description=description, event_date=event_date, event_time=event_time))
        db.session.commit()
        flash("Event added.", "success")
    return redirect(url_for("upcoming.index"))


@upcoming_bp.get("/<int:event_id>")
def detail(event_id):
    event = db.get_or_404(UpcomingEvent, event_id)
    return render_template("upcoming/detail.html", event=event, status_for=status_for, human_date=human_date, human_time=human_time)


@upcoming_bp.post("/<int:event_id>/edit")
def edit(event_id):
    event = db.get_or_404(UpcomingEvent, event_id)
    try:
        event.title, event.description, event.event_date, event.event_time = _validated_values()
    except ValueError as error:
        flash(str(error), "error")
    else:
        db.session.commit()
        flash("Event updated.", "success")
    return redirect(url_for("upcoming.detail", event_id=event.id))


@upcoming_bp.post("/<int:event_id>/delete")
def delete(event_id):
    event = db.get_or_404(UpcomingEvent, event_id)
    db.session.delete(event)
    db.session.commit()
    flash("Event deleted.", "info")
    return redirect(url_for("upcoming.index"))
