import calendar
from datetime import date

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import JournalEntry

journal_bp = Blueprint("journal", __name__, url_prefix="/journal")


@journal_bp.get("/")
def index():
    today = current_date()
    year = parse_number(request.args.get("year"), today.year, 1, 9999)
    month = parse_number(request.args.get("month"), today.month, 1, 12)

    weeks = calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(year, month)
    visible_dates = [day for week in weeks for day in week]
    entry_map = {
        entry.entry_date: entry
        for entry in JournalEntry.query.filter(
            JournalEntry.entry_date.between(visible_dates[0], visible_dates[-1])
        ).all()
    }
    previous_year, previous_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)

    return render_template(
        "journal/calendar.html",
        year=year,
        month=month,
        month_label=date(year, month, 1).strftime("%B %Y"),
        weeks=weeks,
        entry_map=entry_map,
        today=today,
        previous_year=previous_year,
        previous_month=previous_month,
        next_year=next_year,
        next_month=next_month,
    )


@journal_bp.route("/entry/<entry_date>", methods=["GET", "POST"])
def entry(entry_date):
    selected_date = parse_entry_date(entry_date)
    return_year, return_month = parse_return_month(selected_date)
    journal_entry = JournalEntry.query.filter_by(entry_date=selected_date).one_or_none()

    if request.method == "POST":
        body = request.form.get("body", "")
        if journal_entry is None:
            journal_entry = JournalEntry(entry_date=selected_date, body=body)
            db.session.add(journal_entry)
        else:
            journal_entry.body = body

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            abort(409, description="A journal entry already exists for this date.")

        return redirect(
            url_for(
                "journal.entry",
                entry_date=selected_date.isoformat(),
                return_year=return_year,
                return_month=return_month,
                saved=1,
            )
        )

    return render_template(
        "journal/entry.html",
        selected_date=selected_date,
        journal_entry=journal_entry,
        return_year=return_year,
        return_month=return_month,
    )


@journal_bp.post("/entry/<entry_date>/delete")
def delete_entry(entry_date):
    selected_date = parse_entry_date(entry_date)
    return_year, return_month = parse_return_month(selected_date)
    journal_entry = JournalEntry.query.filter_by(entry_date=selected_date).one_or_none()
    if journal_entry is not None:
        db.session.delete(journal_entry)
        db.session.commit()
    return redirect(url_for("journal.index", year=return_year, month=return_month))


def current_date():
    return date.today()


def parse_entry_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        abort(404)


def parse_number(value, default, minimum, maximum):
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        abort(404)
    if not minimum <= number <= maximum:
        abort(404)
    return number


def parse_return_month(selected_date):
    return (
        parse_number(request.values.get("return_year"), selected_date.year, 1, 9999),
        parse_number(request.values.get("return_month"), selected_date.month, 1, 12),
    )


def shift_month(year, month, offset):
    month_index = year * 12 + (month - 1) + offset
    shifted_year, shifted_month_index = divmod(month_index, 12)
    if not 1 <= shifted_year <= 9999:
        return year, month
    return shifted_year, shifted_month_index + 1
