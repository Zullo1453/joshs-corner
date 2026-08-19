from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from ..deadlines import active_deadlines, human_date, status_for
from ..extensions import db
from ..models import Deadline, utc_now


deadlines_bp = Blueprint("deadlines", __name__, url_prefix="/deadlines")


def _form_values():
    return {
        "title": request.form.get("title", "").strip(),
        "description": request.form.get("description", "").strip(),
        "due_date": request.form.get("due_date", "").strip(),
    }


def _validated_values():
    values = _form_values()
    if not values["title"] or len(values["title"]) > 200:
        raise ValueError("Enter a deadline title up to 200 characters.")
    if len(values["description"]) > 5000:
        raise ValueError("Description must be 5,000 characters or fewer.")
    try:
        due_date = date.fromisoformat(values["due_date"])
    except ValueError:
        raise ValueError("Choose a valid due date.") from None
    return values["title"], values["description"], due_date


@deadlines_bp.get("")
def index():
    completed = list(db.session.scalars(
        select(Deadline).where(Deadline.is_completed).order_by(
            Deadline.completed_at.desc(), Deadline.id.desc()
        )
    ))
    return render_template(
        "deadlines/index.html", active_deadlines=active_deadlines(), completed_deadlines=completed,
        status_for=status_for, human_date=human_date,
    )


@deadlines_bp.post("")
def add():
    try:
        title, description, due_date = _validated_values()
    except ValueError as error:
        flash(str(error), "error")
    else:
        db.session.add(Deadline(title=title, description=description, due_date=due_date))
        db.session.commit()
        flash("Deadline added.", "success")
    return redirect(url_for("deadlines.index"))


@deadlines_bp.get("/<int:deadline_id>")
def detail(deadline_id):
    deadline = db.get_or_404(Deadline, deadline_id)
    return render_template("deadlines/detail.html", deadline=deadline, status_for=status_for, human_date=human_date)


@deadlines_bp.post("/<int:deadline_id>/edit")
def edit(deadline_id):
    deadline = db.get_or_404(Deadline, deadline_id)
    try:
        deadline.title, deadline.description, deadline.due_date = _validated_values()
    except ValueError as error:
        flash(str(error), "error")
    else:
        db.session.commit()
        flash("Deadline updated.", "success")
    return redirect(url_for("deadlines.detail", deadline_id=deadline.id))


@deadlines_bp.post("/<int:deadline_id>/complete")
def complete(deadline_id):
    deadline = db.get_or_404(Deadline, deadline_id)
    if not deadline.is_completed:
        deadline.is_completed, deadline.completed_at = True, utc_now()
        db.session.commit()
        flash("Deadline marked complete.", "success")
    return redirect(url_for("deadlines.index"))


@deadlines_bp.post("/<int:deadline_id>/reopen")
def reopen(deadline_id):
    deadline = db.get_or_404(Deadline, deadline_id)
    if deadline.is_completed:
        deadline.is_completed, deadline.completed_at = False, None
        db.session.commit()
        flash("Deadline reopened.", "success")
    return redirect(url_for("deadlines.index"))


@deadlines_bp.post("/<int:deadline_id>/delete")
def delete(deadline_id):
    deadline = db.get_or_404(Deadline, deadline_id)
    db.session.delete(deadline)
    db.session.commit()
    flash("Deadline deleted.", "info")
    return redirect(url_for("deadlines.index"))
