from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from sqlalchemy import or_

from ..extensions import db
from ..attachments import delete_owner_attachments, sync_attachments
from ..models import Note
from ..note_content import sanitise_note_html

notes_bp = Blueprint("notes", __name__, url_prefix="/notes")


@notes_bp.get("/")
def index():
    return render_notes()


@notes_bp.get("/new")
def new():
    return render_notes(new_note=True)


@notes_bp.get("/detail/<int:note_id>")
def detail(note_id):
    note = db.get_or_404(Note, note_id)
    return render_template("notes/_detail.html", selected_note=note, new_note=False, **notes_context())


@notes_bp.post("/new")
def create():
    note = Note(
        title=normalise_title(request.form.get("title")),
        body=sanitise_note_html(request.form.get("body")),
    )
    db.session.add(note)
    db.session.flush()
    sync_attachments(note.body, "note", note.id, request.form.get("body_attachment_token"))
    db.session.commit()
    return redirect_to_notes(note.id)


@notes_bp.post("/<int:note_id>")
def update(note_id):
    note = db.get_or_404(Note, note_id)
    note.title = normalise_title(request.form.get("title"))
    note.body = sanitise_note_html(request.form.get("body"))
    sync_attachments(note.body, "note", note.id, request.form.get("body_attachment_token"))
    db.session.commit()
    if is_partial_request():
        return jsonify(note_save_response(note, request.form))
    return redirect_to_notes(note.id)


@notes_bp.post("/<int:note_id>/autosave")
def autosave(note_id):
    note = db.get_or_404(Note, note_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(status="error", error="Malformed note data."), 400
    title = payload.get("title")
    body = payload.get("body")
    if not isinstance(title, str) or not isinstance(body, str):
        return jsonify(status="error", error="Malformed note data."), 400
    note.title = normalise_title(title)
    note.body = sanitise_note_html(body)
    sync_attachments(note.body, "note", note.id, payload.get("body_attachment_token"))
    db.session.commit()
    return jsonify(note_save_response(note, payload))


@notes_bp.post("/<int:note_id>/favourite")
def toggle_favourite(note_id):
    note = db.get_or_404(Note, note_id)
    note.is_favourite = not note.is_favourite
    db.session.commit()
    if is_partial_request():
        return jsonify(note_save_response(note, request.form))
    return redirect_to_notes(note.id)


@notes_bp.post("/<int:note_id>/delete")
def delete(note_id):
    note = db.get_or_404(Note, note_id)
    delete_owner_attachments("note", note.id)
    db.session.delete(note)
    db.session.commit()
    return redirect_to_notes()


def render_notes(new_note=False):
    context = notes_context()
    notes = context["notes"]
    selected_note = None
    if not new_note and notes:
        selected_id = request.args.get("note_id", type=int)
        selected_note = next((note for note in notes if note.id == selected_id), notes[0])
    return render_template("notes/index.html", selected_note=selected_note, new_note=new_note, **context)


def notes_context():
    query = request.args.get("q", "").strip()
    favourites_only = request.args.get("favourites") == "1"
    statement = db.select(Note)

    if query:
        pattern = f"%{escape_like(query)}%"
        statement = statement.where(
            or_(
                Note.title.ilike(pattern, escape="\\"),
                Note.body.ilike(pattern, escape="\\"),
            )
        )
    if favourites_only:
        statement = statement.where(Note.is_favourite.is_(True))

    notes = db.session.execute(
        statement.order_by(Note.updated_at.desc(), Note.id.desc())
    ).scalars().all()

    return {"notes": notes, "query": query, "favourites_only": favourites_only}


def note_save_response(note, filters):
    query = filters.get("q", "").strip()
    favourites_only = filters.get("favourites") == "1"
    return {"status": "saved", "note_id": note.id, "updated_at": note.updated_at.isoformat(), "sidebar_card_html": render_template("notes/_sidebar_card.html", note=note, selected_note=note, query=query, favourites_only=favourites_only)}


def is_partial_request():
    return request.headers.get("X-Requested-With") == "JoshCornerPartial"


def normalise_title(value):
    title = (value or "").strip()
    return title[:200] or "Untitled note"


def escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def redirect_to_notes(note_id=None):
    parameters = {}
    query = request.form.get("q", "").strip()
    if query:
        parameters["q"] = query
    if request.form.get("favourites") == "1":
        parameters["favourites"] = 1
    if note_id is not None:
        parameters["note_id"] = note_id
    return redirect(url_for("notes.index", **parameters))
