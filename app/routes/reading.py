from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy import or_

from ..extensions import db
from ..models import ReadingItem


reading_bp = Blueprint("reading", __name__, url_prefix="/reading")
VALID_FORMATS = ("Written", "Audible")
VALID_STATUSES = ("To Read", "Reading", "Finished")
VALID_RATING_FILTERS = ("all", "5", "4", "3")
MAX_TITLE_LENGTH = 200


@dataclass
class BookDraft:
    title: str = ""
    format: str = "Written"
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


@reading_bp.post("/new")
def create():
    draft, error = book_from_form()
    if error:
        return render_reading(new_book=True, draft=draft, error=error), 400
    book = ReadingItem(**book_values(draft))
    db.session.add(book)
    db.session.commit()
    return redirect_to_reading(book.id)


@reading_bp.post("/<int:book_id>")
def update(book_id):
    book = db.get_or_404(ReadingItem, book_id)
    draft, error = book_from_form()
    if error:
        return render_reading(selected_book=book, draft=draft, error=error), 400
    for field, value in book_values(draft).items():
        setattr(book, field, value)
    db.session.commit()
    return redirect_to_reading(book.id)


@reading_bp.post("/<int:book_id>/delete")
def delete(book_id):
    book = db.get_or_404(ReadingItem, book_id)
    db.session.delete(book)
    db.session.commit()
    return redirect_to_reading()


def render_reading(new_book=False, selected_book=None, draft=None, error=None):
    if new_book and draft is None:
        draft = BookDraft()
    query = request.args.get("q", "").strip()
    book_format = request.args.get("format", "all")
    status = request.args.get("status", "all")
    rating_filter = request.args.get("rating", "all")
    if book_format != "all" and book_format not in VALID_FORMATS:
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
    if status != "all":
        statement = statement.where(ReadingItem.status == status)
    if rating_filter != "all":
        statement = statement.where(ReadingItem.rating >= float(rating_filter))
    books = db.session.execute(statement.order_by(ReadingItem.updated_at.desc(), ReadingItem.id.desc())).scalars().all()
    if selected_book is None and not new_book and books:
        selected_id = request.args.get("book_id", type=int)
        selected_book = next((book for book in books if book.id == selected_id), books[0])
    return render_template("reading/index.html", books=books, selected_book=selected_book, new_book=new_book, draft=draft, error=error, query=query, book_format=book_format, status=status, rating_filter=rating_filter, formats=VALID_FORMATS, statuses=VALID_STATUSES)


def book_from_form():
    draft = BookDraft(title=(request.form.get("title") or "").strip(), format=request.form.get("format") or "", release_date=(request.form.get("release_date") or "").strip(), status=request.form.get("status") or "", rating=(request.form.get("rating") or "").strip(), notes=request.form.get("notes") or "")
    if not draft.title:
        return draft, "A book title is required."
    if len(draft.title) > MAX_TITLE_LENGTH:
        return draft, f"Book titles must be {MAX_TITLE_LENGTH} characters or fewer."
    if draft.format not in VALID_FORMATS:
        return draft, "Choose Written or Audible."
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
    return {"title": draft.title, "format": draft.format, "release_date": date.fromisoformat(draft.release_date) if draft.release_date else None, "status": draft.status, "rating": float(Decimal(draft.rating)) if draft.rating else None, "notes": draft.notes}


def escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def redirect_to_reading(book_id=None):
    parameters = {}
    query = request.form.get("q", "").strip()
    book_format = request.form.get("filter_format", "all")
    status = request.form.get("filter_status", "all")
    rating_filter = request.form.get("filter_rating", "all")
    if query: parameters["q"] = query
    if book_format in VALID_FORMATS: parameters["format"] = book_format
    if status in VALID_STATUSES: parameters["status"] = status
    if rating_filter in VALID_RATING_FILTERS and rating_filter != "all": parameters["rating"] = rating_filter
    if book_id is not None: parameters["book_id"] = book_id
    return redirect(url_for("reading.index", **parameters))
