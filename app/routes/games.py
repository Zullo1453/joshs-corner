from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import date

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from sqlalchemy import or_

from ..extensions import db
from ..attachments import delete_owner_attachments, sync_attachments
from ..models import GameJournal, GamePlayEntry
from ..note_content import is_visually_empty_html, sanitise_rich_text_html


games_bp = Blueprint("games", __name__, url_prefix="/games")

VALID_STATUSES = ("Playing", "Completed", "Dropped", "Backlog")
MAX_TITLE_LENGTH = 200
MAX_PLATFORM_LENGTH = 100
MAX_HOURS_PLAYED = Decimal("100000")
MAX_PLAY_BODY_LENGTH = 10000


@dataclass
class GameDraft:
    title: str = ""
    status: str = "Backlog"
    rating: str = "0"
    platform: str = ""
    hours_played: str = ""
    notes: str = ""


@dataclass
class PlayEntryDraft:
    played_on: str = ""
    title: str = ""
    body: str = ""


@games_bp.get("/")
def index():
    return render_games()


@games_bp.get("/new")
def new():
    return render_games(new_game=True)


@games_bp.get("/detail/<int:game_id>")
def detail(game_id):
    """Return the existing-game editor fragment for progressive navigation."""
    game = db.get_or_404(GameJournal, game_id)
    context = games_context()
    context["play_entries"] = play_entries_for(game)
    return render_template(
        "games/_detail.html",
        selected_game=game,
        new_game=False,
        draft=None,
        error=None,
        **context,
    )


@games_bp.post("/new")
def create():
    draft, error = game_from_form()
    if error:
        return render_games(new_game=True, draft=draft, error=error), 400

    game = GameJournal(**game_values(draft))
    db.session.add(game)
    db.session.flush()
    sync_attachments(game.notes, "game", game.id, request.form.get("notes_attachment_token"))
    db.session.commit()
    return redirect_to_games(game.id)


@games_bp.post("/<int:game_id>")
def update(game_id):
    game = db.get_or_404(GameJournal, game_id)
    draft, error = game_from_form()
    if error:
        if is_partial_request():
            return jsonify(status="error", error=error), 400
        return render_games(selected_game=game, draft=draft, error=error), 400

    for field, value in game_values(draft).items():
        setattr(game, field, value)
    sync_attachments(game.notes, "game", game.id, request.form.get("notes_attachment_token"))
    play_draft = play_draft_from_form()
    if play_draft_has_content(play_draft):
        play_draft, play_error = play_entry_from_form(play_draft)
        if play_error:
            db.session.commit()
            error = "Your play-entry draft has not been cleared. " + play_error
            if is_partial_request():
                return jsonify(status="error", error=error), 400
            return render_games(
                selected_game=game, draft=draft, play_draft=play_draft,
                play_error=error,
            ), 400
        entry = GamePlayEntry(game=game, **play_entry_values(play_draft))
        db.session.add(entry)
        db.session.flush()
        sync_attachments(entry.body, "game_play", entry.id, request.form.get("play_body_attachment_token"))
    db.session.commit()
    if is_partial_request():
        return jsonify(game_save_response(game, request.form))
    return redirect_to_games(game.id)


@games_bp.post("/<int:game_id>/autosave")
def autosave(game_id):
    game = db.get_or_404(GameJournal, game_id)
    draft, error = game_from_data(request.get_json(silent=True))
    if error:
        return jsonify(status="error", error=error), 400
    for field, value in game_values(draft).items():
        setattr(game, field, value)
    payload = request.get_json(silent=True) or {}
    sync_attachments(game.notes, "game", game.id, payload.get("notes_attachment_token"))
    db.session.commit()
    return jsonify(game_save_response(game, payload))


@games_bp.post("/<int:game_id>/delete")
def delete(game_id):
    game = db.get_or_404(GameJournal, game_id)
    delete_owner_attachments("game", game.id)
    for entry in game.play_entries:
        delete_owner_attachments("game_play", entry.id)
    db.session.delete(game)
    db.session.commit()
    return redirect_to_games()


@games_bp.post("/<int:game_id>/play-log")
def create_play_entry(game_id):
    game = db.get_or_404(GameJournal, game_id)
    draft, error = play_entry_from_form(legacy=True)
    if error:
        return render_games(selected_game=game, play_draft=draft, play_error=error), 400
    entry = GamePlayEntry(game=game, **play_entry_values(draft))
    db.session.add(entry)
    db.session.flush()
    sync_attachments(
        entry.body,
        "game_play",
        entry.id,
        request.form.get("body_attachment_token") or request.form.get("play_body_attachment_token"),
    )
    db.session.commit()
    return redirect_to_games(game.id)


@games_bp.post("/<int:game_id>/play-log/<int:entry_id>")
def update_play_entry(game_id, entry_id):
    game = db.get_or_404(GameJournal, game_id)
    entry = db.get_or_404(GamePlayEntry, entry_id)
    if entry.game_id != game.id:
        abort(404)
    draft, error = play_entry_from_form(legacy=True)
    if error:
        return render_games(selected_game=game, play_draft=draft, play_error=error, editing_entry_id=entry.id), 400
    for field, value in play_entry_values(draft).items():
        setattr(entry, field, value)
    sync_attachments(entry.body, "game_play", entry.id, request.form.get("body_attachment_token"))
    db.session.commit()
    return redirect_to_games(game.id)


@games_bp.post("/<int:game_id>/play-log/<int:entry_id>/autosave")
def autosave_play_entry(game_id, entry_id):
    game = db.get_or_404(GameJournal, game_id)
    entry = db.get_or_404(GamePlayEntry, entry_id)
    if entry.game_id != game.id:
        abort(404)
    payload = request.get_json(silent=True)
    draft, error = play_entry_from_data(payload)
    if error:
        return jsonify(status="error", error=error), 400
    for field, value in play_entry_values(draft).items():
        setattr(entry, field, value)
    sync_attachments(entry.body, "game_play", entry.id, payload.get("body_attachment_token"))
    db.session.commit()
    return jsonify(status="saved", entry_id=entry.id, updated_at=entry.updated_at.isoformat())


@games_bp.post("/<int:game_id>/play-log/<int:entry_id>/delete")
def delete_play_entry(game_id, entry_id):
    game = db.get_or_404(GameJournal, game_id)
    entry = db.get_or_404(GamePlayEntry, entry_id)
    if entry.game_id != game.id:
        abort(404)
    delete_owner_attachments("game_play", entry.id)
    db.session.delete(entry)
    db.session.commit()
    return redirect_to_games(game.id)


def render_games(new_game=False, selected_game=None, draft=None, error=None, play_draft=None, play_error=None, editing_entry_id=None):
    context = games_context()
    games = context["games"]
    if new_game and draft is None:
        draft = GameDraft()
    if selected_game is None and not new_game and games:
        selected_id = request.args.get("game_id", type=int)
        selected_game = next((game for game in games if game.id == selected_id), games[0])
    context["play_entries"] = play_entries_for(selected_game)
    return render_template(
        "games/index.html",
        selected_game=selected_game,
        new_game=new_game,
        draft=draft,
        error=error,
        play_draft=play_draft,
        play_error=play_error,
        editing_entry_id=editing_entry_id,
        **context,
    )


def games_context():
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "all")
    if status != "all" and status not in VALID_STATUSES:
        abort(400)

    statement = db.select(GameJournal)
    if query:
        pattern = f"%{escape_like(query)}%"
        statement = statement.where(
            or_(
                GameJournal.title.ilike(pattern, escape="\\"),
                GameJournal.notes.ilike(pattern, escape="\\"),
            )
        )
    if status != "all":
        statement = statement.where(GameJournal.status == status)

    games = db.session.execute(
        statement.order_by(GameJournal.updated_at.desc(), GameJournal.id.desc())
    ).scalars().all()

    return {
        "games": games,
        "query": query,
        "status": status,
        "statuses": VALID_STATUSES,
    }


def play_entries_for(game):
    if game is None:
        return []
    return sorted(
        game.play_entries,
        key=lambda entry: (entry.played_on, entry.created_at, entry.id),
        reverse=True,
    )


def game_save_response(game, filters):
    """Return authoritative sidebar markup without replacing the sidebar."""
    context = game_filters(filters)
    return {
        "status": "saved",
        "game_id": game.id,
        "updated_at": game.updated_at.isoformat(),
        "sidebar_card_html": render_template(
            "games/_sidebar_card.html",
            listed_game=game,
            selected_game=game,
            **context,
        ),
    }


def game_filters(data):
    return {
        "query": data.get("q", "").strip(),
        "status": data.get("filter_status", data.get("status", "all")),
    }


def is_partial_request():
    return request.headers.get("X-Requested-With") == "JoshCornerPartial"


def game_from_form():
    return game_from_data(request.form)


def game_from_data(data):
    if not hasattr(data, "get"):
        return GameDraft(), "Malformed game data."
    fields = {name: data.get(name, "") for name in ("title", "status", "rating", "platform", "hours_played", "notes")}
    if not all(isinstance(value, str) for value in fields.values()):
        return GameDraft(), "Malformed game data."
    draft = GameDraft(title=fields["title"].strip(), status=fields["status"].strip(), rating=fields["rating"].strip(), platform=fields["platform"].strip(), hours_played=fields["hours_played"].strip(), notes=sanitise_rich_text_html(fields["notes"]))
    if not draft.title:
        return draft, "A game title is required."
    if len(draft.title) > MAX_TITLE_LENGTH:
        return draft, f"Game titles must be {MAX_TITLE_LENGTH} characters or fewer."
    if draft.status not in VALID_STATUSES:
        return draft, "Choose a valid game status."
    if len(draft.platform) > MAX_PLATFORM_LENGTH:
        return draft, f"Platforms must be {MAX_PLATFORM_LENGTH} characters or fewer."

    try:
        rating = Decimal(draft.rating) if draft.rating else None
    except InvalidOperation:
        return draft, "Choose a rating from 0 to 5."
    if rating is not None and (
        rating < 0 or rating > 5 or (rating * 2) != (rating * 2).to_integral_value()
    ):
        return draft, "Ratings must be in half-star increments from 0 to 5."

    try:
        hours = Decimal(draft.hours_played) if draft.hours_played else None
    except InvalidOperation:
        return draft, "Hours played must be a number."
    if hours is not None and (hours < 0 or hours > MAX_HOURS_PLAYED):
        return draft, f"Hours played must be between 0 and {MAX_HOURS_PLAYED}."
    return draft, None


def game_values(draft):
    return {
        "title": draft.title,
        "status": draft.status,
        "rating": float(Decimal(draft.rating)) if draft.rating else None,
        "platform": draft.platform,
        "hours_played": float(Decimal(draft.hours_played)) if draft.hours_played else None,
        "notes": draft.notes,
    }


def play_draft_from_form(legacy=False):
    return PlayEntryDraft(
        played_on=(request.form.get("played_on") or "").strip(),
        title=(request.form.get("play_title") or (request.form.get("title") if legacy else "") or "").strip(),
        body=sanitise_rich_text_html(request.form.get("play_body") or (request.form.get("body") if legacy else "") or ""),
    )


def play_draft_has_content(draft):
    return bool(draft.played_on or draft.title or not is_visually_empty_html(draft.body))


def play_entry_from_form(draft=None, legacy=False):
    draft = draft or play_draft_from_form(legacy=legacy)
    try:
        date.fromisoformat(draft.played_on)
    except ValueError:
        return draft, "Choose a valid date played."
    if len(draft.title) > MAX_TITLE_LENGTH:
        return draft, f"Play-entry titles must be {MAX_TITLE_LENGTH} characters or fewer."
    if is_visually_empty_html(draft.body):
        return draft, "A play-entry body is required."
    if len(draft.body) > MAX_PLAY_BODY_LENGTH:
        return draft, f"Play entries must be {MAX_PLAY_BODY_LENGTH} characters or fewer."
    return draft, None


def play_entry_from_data(data):
    if not hasattr(data, "get"):
        return PlayEntryDraft(), "Malformed play-entry data."
    fields = {name: data.get(name, "") for name in ("played_on", "title", "body")}
    if not all(isinstance(value, str) for value in fields.values()):
        return PlayEntryDraft(), "Malformed play-entry data."
    return play_entry_from_form(PlayEntryDraft(played_on=fields["played_on"].strip(), title=fields["title"].strip(), body=sanitise_rich_text_html(fields["body"])))


def play_entry_values(draft):
    return {"played_on": date.fromisoformat(draft.played_on), "title": draft.title, "body": "" if is_visually_empty_html(draft.body) else draft.body}


def escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def redirect_to_games(game_id=None):
    parameters = {}
    query = request.form.get("q", "").strip()
    status = request.form.get("filter_status", "all")
    if query:
        parameters["q"] = query
    if status in VALID_STATUSES:
        parameters["status"] = status
    if game_id is not None:
        parameters["game_id"] = game_id
    return redirect(url_for("games.index", **parameters))
