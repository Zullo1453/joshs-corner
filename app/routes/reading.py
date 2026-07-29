from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from sqlalchemy import or_

from ..extensions import db
from ..attachments import delete_owner_attachments, sync_attachments
from ..models import ReadingItem
from ..note_content import sanitise_rich_text_html


reading_bp = Blueprint("reading", __name__, url_prefix="/reading")
VALID_FORMATS = ("Written", "Audible")
VALID_STATUSES = ("To Read", "Reading", "Finished")
VALID_RATING_FILTERS = ("all", "5", "4", "3")
VALID_BOOK_TYPES = ("fiction", "non_fiction")
VALID_BOOK_TYPE_FILTERS = ("all", *VALID_BOOK_TYPES, "unclassified")
MAX_TITLE_LENGTH = 200


@dataclass
class BookDraft:
    title: str = ""
    format: str = "Written"
    book_type: str = ""
    release_date: str = ""
    status: str = "To Read"
    rating: str = "0"
    notes: str = ""


@reading_bp.get("/")
def index():
    return render_reading()


@reading_bp.get("/new")
def new():
    return render_reading(new_book=True)


@reading_bp.get("/detail/<int:book_id>")
def detail(book_id):
    """Return the existing-book editor fragment for progressive navigation.

    The normal Reading List route remains the source of truth for complete,
    bookmarkable pages.  This endpoint deliberately accepts only a validated
    integer record ID and renders the same editor partial used by that page.
    """
    book = db.get_or_404(ReadingItem, book_id)
    context = reading_context()
    return render_template(
        "reading/_detail.html",
        selected_book=book,
        new_book=False,
        draft=None,
        error=None,
        **context,
    )


@reading_bp.post("/new")
def create():
    draft, error = book_from_form(allow_unclassified=False)
    if error:
        return render_reading(new_book=True, draft=draft, error=error), 400
    book = ReadingItem(**book_values(draft))
    db.session.add(book)
    db.session.flush()
    sync_attachments(book.notes, "reading", book.id, request.form.get("notes_attachment_token"))
    db.session.commit()
    return redirect_to_reading(book.id)


@reading_bp.post("/<int:book_id>")
def update(book_id):
    book = db.get_or_404(ReadingItem, book_id)
    draft, error = book_from_form(allow_unclassified=True)
    if error:
        return render_reading(selected_book=book, draft=draft, error=error), 400
    for field, value in book_values(draft).items():
        setattr(book, field, value)
    sync_attachments(book.notes, "reading", book.id, request.form.get("notes_attachment_token"))
    db.session.commit()
    if is_partial_request():
        return jsonify(reading_save_response(book, request.form))
    return redirect_to_reading(book.id)


@reading_bp.post("/<int:book_id>/autosave")
def autosave(book_id):
    book = db.get_or_404(ReadingItem, book_id)
    payload = request.get_json(silent=True)
    draft, error = book_from_data(payload, allow_unclassified=True)
    if error:
        return jsonify(status="error", error=error), 400
    for field, value in book_values(draft).items():
        setattr(book, field, value)
    sync_attachments(book.notes, "reading", book.id, payload.get("notes_attachment_token"))
    db.session.commit()
    return jsonify(reading_save_response(book, payload))


@reading_bp.post("/<int:book_id>/delete")
def delete(book_id):
    book = db.get_or_404(ReadingItem, book_id)
    delete_owner_attachments("reading", book.id)
    db.session.delete(book)
    db.session.commit()
    return redirect_to_reading()


def render_reading(new_book=False, selected_book=None, draft=None, error=None):
    context = reading_context()
    books = context["books"]
    if new_book and draft is None:
        draft = BookDraft()
    if selected_book is None and not new_book and books:
        selected_id = request.args.get("book_id", type=int)
        selected_book = next((book for book in books if book.id == selected_id), books[0])
    return render_template(
        "reading/index.html",
        selected_book=selected_book,
        new_book=new_book,
        draft=draft,
        error=error,
        **context,
    )


def reading_context():
    query = request.args.get("q", "").strip()
    book_format = request.args.get("format", "all")
    book_type_filter = request.args.get("type", "all")
    status = request.args.get("status", "all")
    rating_filter = request.args.get("rating", "all")
    if book_format != "all" and book_format not in VALID_FORMATS:
        abort(400)
    if book_type_filter not in VALID_BOOK_TYPE_FILTERS:
        abort(400)
    if status != "all" and status not in VALID_STATUSES:
        abort(400)
    if rating_filter not in VALID_RATING_FILTERS:
        abort(400)
    statement = db.select(ReadingItem)
    if query:
        pattern = f"%{escape_like(query)}%"
        statement = statement.where(or_(ReadingItem.title.ilike(pattern, escape="\\"), ReadingItem.notes.ilike(pattern, escape="\\")))
    if book_format != "all":
        statement = statement.where(ReadingItem.format == book_format)
    if book_type_filter in VALID_BOOK_TYPES:
        statement = statement.where(ReadingItem.book_type == book_type_filter)
    elif book_type_filter == "unclassified":
        statement = statement.where(ReadingItem.book_type.is_(None))
    if status != "all":
        statement = statement.where(ReadingItem.status == status)
    if rating_filter != "all":
        statement = statement.where(ReadingItem.rating >= float(rating_filter))
    books = db.session.execute(statement.order_by(ReadingItem.updated_at.desc(), ReadingItem.id.desc())).scalars().all()
    return {
        "books": books,
        "query": query,
        "book_format": book_format,
        "book_type_filter": book_type_filter,
        "status": status,
        "rating_filter": rating_filter,
        "formats": VALID_FORMATS,
        "statuses": VALID_STATUSES,
        "book_types": VALID_BOOK_TYPES,
    }


def reading_save_response(book, filters):
    """Return server-rendered sidebar data for an in-place Reading List save."""
    context = reading_filters(filters)
    return {
        "status": "saved",
        "book_id": book.id,
        "updated_at": book.updated_at.isoformat(),
        "sidebar_card_html": render_template(
            "reading/_sidebar_card.html",
            listed_book=book,
            selected_book=book,
            **context,
        ),
    }


def reading_filters(data):
    query = data.get("q", "").strip()
    book_format = data.get("filter_format", data.get("format", "all"))
    book_type_filter = data.get("filter_type", data.get("type", "all"))
    status = data.get("filter_status", data.get("status", "all"))
    rating_filter = data.get("filter_rating", data.get("rating", "all"))
    return {
        "query": query,
        "book_format": book_format,
        "book_type_filter": book_type_filter,
        "status": status,
        "rating_filter": rating_filter,
    }


def is_partial_request():
    return request.headers.get("X-Requested-With") == "JoshCornerPartial"


def book_from_form(allow_unclassified):
    return book_from_data(request.form, allow_unclassified)


def book_from_data(data, allow_unclassified):
    if not isinstance(data, dict) and not hasattr(data, "get"):
        return BookDraft(), "Malformed book data."

    def text_value(name):
        value = data.get(name, "")
        return value.strip() if isinstance(value, str) else None

    title = text_value("title")
    book_format = text_value("format")
    book_type = text_value("book_type")
    release_date = text_value("release_date")
    status = text_value("status")
    rating = text_value("rating")
    notes = text_value("notes")
    if None in (title, book_format, book_type, release_date, status, rating, notes):
        return BookDraft(), "Malformed book data."
    draft = BookDraft(
        title=title,
        format=book_format,
        book_type=book_type,
        release_date=release_date,
        status=status,
        rating=rating,
        notes=sanitise_rich_text_html(notes),
    )
    if not draft.title:
        return draft, "A book title is required."
    if len(draft.title) > MAX_TITLE_LENGTH:
        return draft, f"Book titles must be {MAX_TITLE_LENGTH} characters or fewer."
    if draft.format not in VALID_FORMATS:
        return draft, "Choose Written or Audible."
    if draft.book_type not in VALID_BOOK_TYPES and not (allow_unclassified and not draft.book_type):
        return draft, "Choose Fiction or Non-Fiction."
    if draft.status not in VALID_STATUSES:
        return draft, "Choose a valid reading status."
    try:
        rating = Decimal(draft.rating) if draft.rating else None
    except InvalidOperation:
        return draft, "Choose a rating from 0 to 5."
    if rating is not None and (rating < 0 or rating > 5 or (rating * 2) != (rating * 2).to_integral_value()):
        return draft, "Ratings must be in half-star increments from 0 to 5."
    if draft.release_date:
        try:
            date.fromisoformat(draft.release_date)
        except ValueError:
            return draft, "Enter a valid release date."
    return draft, None


def book_values(draft):
    return {"title": draft.title, "format": draft.format, "book_type": draft.book_type or None, "release_date": date.fromisoformat(draft.release_date) if draft.release_date else None, "status": draft.status, "rating": float(Decimal(draft.rating)) if draft.rating else None, "notes": draft.notes}


def escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def redirect_to_reading(book_id=None):
    parameters = {}
    query = request.form.get("q", "").strip()
    book_format = request.form.get("filter_format", "all")
    book_type_filter = request.form.get("filter_type", "all")
    status = request.form.get("filter_status", "all")
    rating_filter = request.form.get("filter_rating", "all")
    if query: parameters["q"] = query
    if book_format in VALID_FORMATS: parameters["format"] = book_format
    if book_type_filter in VALID_BOOK_TYPE_FILTERS and book_type_filter != "all": parameters["type"] = book_type_filter
    if status in VALID_STATUSES: parameters["status"] = status
    if rating_filter in VALID_RATING_FILTERS and rating_filter != "all": parameters["rating"] = rating_filter
    if book_id is not None: parameters["book_id"] = book_id
    return redirect(url_for("reading.index", **parameters))
