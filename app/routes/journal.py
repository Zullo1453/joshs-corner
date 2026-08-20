import calendar
from dataclasses import dataclass
from datetime import date, time

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..attachments import delete_owner_attachments, sync_attachments
from ..models import Deadline, JournalEntry, UpcomingEvent
from ..note_content import sanitise_rich_text_html

journal_bp = Blueprint("journal", __name__, url_prefix="/journal")


@dataclass(frozen=True)
class JournalLinkValues:
    deadline_enabled: bool
    deadline_title: str = ""
    due_date: date | None = None
    upcoming_enabled: bool = False
    upcoming_title: str = ""
    event_date: date | None = None
    event_time: time | None = None


class JournalLinkValidationError(ValueError):
    pass


class JournalLinkConfirmationRequired(ValueError):
    pass


@journal_bp.get("/")
def index():
    today = current_date()
    year = parse_number(request.args.get("year"), today.year, 2, 9998)
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
        month_label=date(year, month, 1).strftime("%B"),
        year_options=journal_year_options(year, today.year),
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
        body = sanitise_rich_text_html(request.form.get("body", ""))
        try:
            link_values = validated_link_values(request.form)
            validate_link_removals(journal_entry, link_values, request.form)
        except (JournalLinkValidationError, JournalLinkConfirmationRequired) as error:
            return render_entry(
                selected_date, journal_entry, return_year, return_month, form_body=body,
                integration_error=str(error), submitted_form=request.form,
            ), 400
        if journal_entry is None:
            journal_entry = JournalEntry(entry_date=selected_date, body=body)
            db.session.add(journal_entry)
        else:
            journal_entry.body = body

        try:
            db.session.flush()
            sync_attachments(body, "journal", journal_entry.id, request.form.get("body_attachment_token"))
            sync_journal_links(journal_entry, link_values)
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

    return render_entry(selected_date, journal_entry, return_year, return_month)


@journal_bp.post("/entry/<entry_date>/delete")
def delete_entry(entry_date):
    selected_date = parse_entry_date(entry_date)
    return_year, return_month = parse_return_month(selected_date)
    journal_entry = JournalEntry.query.filter_by(entry_date=selected_date).one_or_none()
    if journal_entry is not None:
        if journal_entry.deadline_link is not None:
            journal_entry.deadline_link.source_journal_entry_id = None
        if journal_entry.upcoming_link is not None:
            journal_entry.upcoming_link.source_journal_entry_id = None
        delete_owner_attachments("journal", journal_entry.id)
        db.session.delete(journal_entry)
        db.session.commit()
    return redirect(url_for("journal.index", year=return_year, month=return_month))


@journal_bp.post("/entry/<entry_date>/autosave")
def autosave_entry(entry_date):
    selected_date = parse_entry_date(entry_date)
    journal_entry = JournalEntry.query.filter_by(entry_date=selected_date).one_or_none()
    if journal_entry is None:
        abort(404)
    payload = request.get_json(silent=True)
    body = payload.get("body") if isinstance(payload, dict) else None
    if not isinstance(body, str):
        return jsonify(status="error", error="Malformed journal data."), 400
    journal_entry.body = sanitise_rich_text_html(body)
    sync_attachments(journal_entry.body, "journal", journal_entry.id, payload.get("body_attachment_token"))
    db.session.commit()
    return jsonify(status="saved", entry_id=journal_entry.id, updated_at=journal_entry.updated_at.isoformat())


def current_date():
    return date.today()


def default_link_title(selected_date):
    return f"Journal entry — {selected_date.day} {selected_date.strftime('%B %Y')}"


def validated_link_values(form):
    deadline_enabled = form.get("link_deadline") == "1"
    upcoming_enabled = form.get("link_upcoming") == "1"
    deadline_title = form.get("deadline_title", "").strip()
    upcoming_title = form.get("upcoming_title", "").strip()

    due_date = None
    if deadline_enabled:
        if not deadline_title or len(deadline_title) > 200:
            raise JournalLinkValidationError("Enter a deadline title up to 200 characters.")
        try:
            due_date = date.fromisoformat(form.get("deadline_due_date", "").strip())
        except ValueError:
            raise JournalLinkValidationError("Choose a valid deadline date.") from None

    event_date = event_time = None
    if upcoming_enabled:
        if not upcoming_title or len(upcoming_title) > 200:
            raise JournalLinkValidationError("Enter an event title up to 200 characters.")
        try:
            event_date = date.fromisoformat(form.get("upcoming_event_date", "").strip())
        except ValueError:
            raise JournalLinkValidationError("Choose a valid event date.") from None
        try:
            event_time_raw = form.get("upcoming_event_time", "").strip()
            event_time = time.fromisoformat(event_time_raw) if event_time_raw else None
        except ValueError:
            raise JournalLinkValidationError("Choose a valid event time.") from None

    return JournalLinkValues(
        deadline_enabled=deadline_enabled, deadline_title=deadline_title, due_date=due_date,
        upcoming_enabled=upcoming_enabled, upcoming_title=upcoming_title,
        event_date=event_date, event_time=event_time,
    )


def validate_link_removals(journal_entry, values, form):
    if journal_entry is None:
        return
    if journal_entry.deadline_link is not None and not values.deadline_enabled and form.get("confirm_remove_deadline") != "1":
        raise JournalLinkConfirmationRequired("Confirm removal of the linked Deadline before saving.")
    if journal_entry.upcoming_link is not None and not values.upcoming_enabled and form.get("confirm_remove_upcoming") != "1":
        raise JournalLinkConfirmationRequired("Confirm removal of the linked Upcoming event before saving.")


def sync_journal_links(journal_entry, values):
    deadline = journal_entry.deadline_link
    if values.deadline_enabled:
        if deadline is None:
            db.session.add(Deadline(
                title=values.deadline_title, due_date=values.due_date, source_journal_entry=journal_entry,
            ))
        else:
            deadline.title, deadline.due_date = values.deadline_title, values.due_date
    elif deadline is not None:
        db.session.delete(deadline)

    upcoming = journal_entry.upcoming_link
    if values.upcoming_enabled:
        if upcoming is None:
            db.session.add(UpcomingEvent(
                title=values.upcoming_title, event_date=values.event_date,
                event_time=values.event_time, source_journal_entry=journal_entry,
            ))
        else:
            upcoming.title, upcoming.event_date, upcoming.event_time = (
                values.upcoming_title, values.event_date, values.event_time,
            )
    elif upcoming is not None:
        db.session.delete(upcoming)


def entry_integration_form(selected_date, journal_entry, submitted_form=None):
    deadline = journal_entry.deadline_link if journal_entry is not None else None
    upcoming = journal_entry.upcoming_link if journal_entry is not None else None
    if submitted_form is not None:
        return {
            "deadline_enabled": submitted_form.get("link_deadline") == "1",
            "deadline_title": submitted_form.get("deadline_title", default_link_title(selected_date)),
            "deadline_due_date": submitted_form.get("deadline_due_date", selected_date.isoformat()),
            "upcoming_enabled": submitted_form.get("link_upcoming") == "1",
            "upcoming_title": submitted_form.get("upcoming_title", default_link_title(selected_date)),
            "upcoming_event_date": submitted_form.get("upcoming_event_date", selected_date.isoformat()),
            "upcoming_event_time": submitted_form.get("upcoming_event_time", ""),
            "has_deadline_link": deadline is not None,
            "has_upcoming_link": upcoming is not None,
        }
    return {
        "deadline_enabled": deadline is not None,
        "deadline_title": deadline.title if deadline is not None else default_link_title(selected_date),
        "deadline_due_date": deadline.due_date.isoformat() if deadline is not None else selected_date.isoformat(),
        "upcoming_enabled": upcoming is not None,
        "upcoming_title": upcoming.title if upcoming is not None else default_link_title(selected_date),
        "upcoming_event_date": upcoming.event_date.isoformat() if upcoming is not None else selected_date.isoformat(),
        "upcoming_event_time": upcoming.event_time.isoformat() if upcoming is not None and upcoming.event_time else "",
        "has_deadline_link": deadline is not None,
        "has_upcoming_link": upcoming is not None,
    }


def render_entry(selected_date, journal_entry, return_year, return_month, form_body=None, integration_error=None, submitted_form=None):
    return render_template(
        "journal/entry.html", selected_date=selected_date, journal_entry=journal_entry,
        return_year=return_year, return_month=return_month, form_body=form_body,
        integration_error=integration_error,
        integration_form=entry_integration_form(selected_date, journal_entry, submitted_form),
    )


def parse_entry_date(value):
    try:
        selected_date = date.fromisoformat(value)
    except (TypeError, ValueError):
        abort(404)
    if not 2 <= selected_date.year <= 9998:
        abort(404)
    return selected_date


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
        parse_number(request.values.get("return_year"), selected_date.year, 2, 9998),
        parse_number(request.values.get("return_month"), selected_date.month, 1, 12),
    )


def shift_month(year, month, offset):
    month_index = year * 12 + (month - 1) + offset
    shifted_year, shifted_month_index = divmod(month_index, 12)
    if not 2 <= shifted_year <= 9998:
        return year, month
    return shifted_year, shifted_month_index + 1


def journal_year_options(selected_year, current_year):
    earliest_year, latest_year = db.session.execute(
        db.select(
            func.min(func.extract("year", JournalEntry.entry_date)),
            func.max(func.extract("year", JournalEntry.entry_date)),
        )
    ).one()

    if earliest_year is None:
        first_year = current_year - 10
        last_year = current_year + 10
    else:
        first_year = min(int(earliest_year), current_year) - 5
        last_year = max(int(latest_year), current_year) + 5

    first_year = max(2, min(first_year, selected_year))
    last_year = min(9998, max(last_year, selected_year))
    return range(first_year, last_year + 1)
