from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from sqlalchemy import or_

from ..extensions import db
from ..attachments import delete_owner_attachments, sync_attachments
from ..models import WatchlistItem
from ..note_content import sanitise_rich_text_html


watchlist_bp = Blueprint("watchlist", __name__, url_prefix="/watchlist")

VALID_TYPES = ("Movie", "Show")
VALID_STATUSES = ("Want to Watch", "Watching", "Finished")
MAX_TITLE_LENGTH = 200
MAX_GENRE_LENGTH = 100
MAX_RECOMMENDATION_LENGTH = 2000
MIN_RELEASE_YEAR = 1888
MAX_RELEASE_YEAR = 2100


@dataclass
class WatchDraft:
    title: str = ""
    media_type: str = "Movie"
    status: str = "Want to Watch"
    rating: str = "0"
    release_year: str = ""
    genre: str = ""
    recommendation_note: str = ""
    notes: str = ""


@watchlist_bp.get("/")
def index():
    return render_watchlist()


@watchlist_bp.get("/new")
def new():
    return render_watchlist(new_item=True)


@watchlist_bp.get("/detail/<int:item_id>")
def detail(item_id):
    item = db.get_or_404(WatchlistItem, item_id)
    return render_template("watchlist/_detail.html", selected_item=item, new_item=False, draft=None, error=None, **watchlist_context())


@watchlist_bp.post("/new")
def create():
    draft, error = item_from_form()
    if error:
        return render_watchlist(new_item=True, draft=draft, error=error), 400
    item = WatchlistItem(**item_values(draft))
    db.session.add(item)
    db.session.flush()
    sync_attachments(item.notes, "watchlist", item.id, request.form.get("notes_attachment_token"))
    db.session.commit()
    return redirect_to_watchlist(item.id)


@watchlist_bp.post("/<int:item_id>")
def update(item_id):
    item = db.get_or_404(WatchlistItem, item_id)
    draft, error = item_from_form()
    if error:
        return render_watchlist(selected_item=item, draft=draft, error=error), 400
    for field, value in item_values(draft).items():
        setattr(item, field, value)
    sync_attachments(item.notes, "watchlist", item.id, request.form.get("notes_attachment_token"))
    db.session.commit()
    if is_partial_request():
        return jsonify(watch_save_response(item, request.form))
    return redirect_to_watchlist(item.id)


@watchlist_bp.post("/<int:item_id>/autosave")
def autosave(item_id):
    item = db.get_or_404(WatchlistItem, item_id)
    payload = request.get_json(silent=True)
    draft, error = item_from_data(payload)
    if error:
        return jsonify(status="error", error=error), 400
    for field, value in item_values(draft).items():
        setattr(item, field, value)
    sync_attachments(item.notes, "watchlist", item.id, payload.get("notes_attachment_token"))
    db.session.commit()
    return jsonify(watch_save_response(item, payload))


@watchlist_bp.post("/<int:item_id>/delete")
def delete(item_id):
    item = db.get_or_404(WatchlistItem, item_id)
    delete_owner_attachments("watchlist", item.id)
    db.session.delete(item)
    db.session.commit()
    return redirect_to_watchlist()


def render_watchlist(new_item=False, selected_item=None, draft=None, error=None):
    context = watchlist_context()
    items = context["items"]
    if new_item and draft is None:
        draft = WatchDraft()
    if selected_item is None and not new_item and items:
        selected_id = request.args.get("item_id", type=int)
        selected_item = next((item for item in items if item.id == selected_id), items[0])
    return render_template("watchlist/index.html", selected_item=selected_item, new_item=new_item, draft=draft, error=error, **context)


def watchlist_context():
    query = request.args.get("q", "").strip()
    media_type = request.args.get("type", "all")
    status = request.args.get("status", "all")
    genre = request.args.get("genre", "all").strip()
    if media_type != "all" and media_type not in VALID_TYPES:
        abort(400)
    if status != "all" and status not in VALID_STATUSES:
        abort(400)

    statement = db.select(WatchlistItem)
    if query:
        pattern = f"%{escape_like(query)}%"
        statement = statement.where(
            or_(
                WatchlistItem.title.ilike(pattern, escape="\\"),
                WatchlistItem.recommendation_note.ilike(pattern, escape="\\"),
                WatchlistItem.notes.ilike(pattern, escape="\\"),
            )
        )
    if media_type != "all":
        statement = statement.where(WatchlistItem.media_type == media_type)
    if status != "all":
        statement = statement.where(WatchlistItem.status == status)
    if genre != "all":
        statement = statement.where(WatchlistItem.genre == genre)

    items = db.session.execute(
        statement.order_by(WatchlistItem.updated_at.desc(), WatchlistItem.id.desc())
    ).scalars().all()
    genres = db.session.execute(
        db.select(WatchlistItem.genre)
        .where(WatchlistItem.genre != "")
        .distinct()
        .order_by(WatchlistItem.genre)
    ).scalars().all()
    return {
        "items": items,
        "query": query,
        "media_type": media_type,
        "status": status,
        "genre": genre,
        "genres": genres,
        "types": VALID_TYPES,
        "statuses": VALID_STATUSES,
    }


def watch_save_response(item, filters):
    context = watch_filters(filters)
    return {"status": "saved", "item_id": item.id, "updated_at": item.updated_at.isoformat(), "sidebar_card_html": render_template("watchlist/_sidebar_card.html", listed_item=item, selected_item=item, **context)}


def watch_filters(data):
    return {"query": data.get("q", "").strip(), "media_type": data.get("filter_type", data.get("type", "all")), "status": data.get("filter_status", data.get("status", "all")), "genre": data.get("filter_genre", data.get("genre", "all")).strip()}


def is_partial_request():
    return request.headers.get("X-Requested-With") == "JoshCornerPartial"


def item_from_form():
    return item_from_data(request.form)


def item_from_data(data):
    if not hasattr(data, "get"):
        return WatchDraft(), "Malformed watchlist data."
    fields = {name: data.get(name, "") for name in ("title", "media_type", "status", "rating", "release_year", "genre", "recommendation_note", "notes")}
    if not all(isinstance(value, str) for value in fields.values()):
        return WatchDraft(), "Malformed watchlist data."
    draft = WatchDraft(title=fields["title"].strip(), media_type=fields["media_type"].strip(), status=fields["status"].strip(), rating=fields["rating"].strip(), release_year=fields["release_year"].strip(), genre=fields["genre"].strip(), recommendation_note=fields["recommendation_note"].strip(), notes=sanitise_rich_text_html(fields["notes"]))
    if not draft.title:
        return draft, "A title is required."
    if len(draft.title) > MAX_TITLE_LENGTH:
        return draft, f"Titles must be {MAX_TITLE_LENGTH} characters or fewer."
    if draft.media_type not in VALID_TYPES:
        return draft, "Choose Movie or Show."
    if draft.status not in VALID_STATUSES:
        return draft, "Choose a valid watch status."
    if len(draft.genre) > MAX_GENRE_LENGTH:
        return draft, f"Genres must be {MAX_GENRE_LENGTH} characters or fewer."
    if len(draft.recommendation_note) > MAX_RECOMMENDATION_LENGTH:
        return draft, f"Recommendation notes must be {MAX_RECOMMENDATION_LENGTH} characters or fewer."
    try:
        rating = Decimal(draft.rating) if draft.rating else None
    except InvalidOperation:
        return draft, "Choose a rating from 0 to 5."
    if rating is not None and (
        rating < 0 or rating > 5 or (rating * 2) != (rating * 2).to_integral_value()
    ):
        return draft, "Ratings must be in half-star increments from 0 to 5."
    try:
        release_year = int(draft.release_year) if draft.release_year else None
    except ValueError:
        return draft, f"Release year must be between {MIN_RELEASE_YEAR} and {MAX_RELEASE_YEAR}."
    if release_year is not None and not MIN_RELEASE_YEAR <= release_year <= MAX_RELEASE_YEAR:
        return draft, f"Release year must be between {MIN_RELEASE_YEAR} and {MAX_RELEASE_YEAR}."
    return draft, None


def item_values(draft):
    return {
        "title": draft.title,
        "media_type": draft.media_type,
        "status": draft.status,
        "rating": float(Decimal(draft.rating)) if draft.rating else None,
        "release_year": int(draft.release_year) if draft.release_year else None,
        "genre": draft.genre,
        "recommendation_note": draft.recommendation_note,
        "notes": draft.notes,
    }


def escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def redirect_to_watchlist(item_id=None):
    parameters = {}
    query = request.form.get("q", "").strip()
    media_type = request.form.get("filter_type", "all")
    status = request.form.get("filter_status", "all")
    genre = request.form.get("filter_genre", "all").strip()
    if query:
        parameters["q"] = query
    if media_type in VALID_TYPES:
        parameters["type"] = media_type
    if status in VALID_STATUSES:
        parameters["status"] = status
    if genre and genre != "all":
        parameters["genre"] = genre
    if item_id is not None:
        parameters["item_id"] = item_id
    return redirect(url_for("watchlist.index", **parameters))
