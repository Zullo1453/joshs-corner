from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy import or_

from ..extensions import db
from ..models import GameJournal


games_bp = Blueprint("games", __name__, url_prefix="/games")

VALID_STATUSES = ("Playing", "Completed", "Dropped", "Backlog")
MAX_TITLE_LENGTH = 200
MAX_PLATFORM_LENGTH = 100
MAX_HOURS_PLAYED = Decimal("100000")


@dataclass
class GameDraft:
    title: str = ""
    status: str = "Backlog"
    rating: str = "0"
    platform: str = ""
    hours_played: str = ""
    notes: str = ""


@games_bp.get("/")
def index():
    return render_games()


@games_bp.get("/new")
def new():
    return render_games(new_game=True)


@games_bp.post("/new")
def create():
    draft, error = game_from_form()
    if error:
        return render_games(new_game=True, draft=draft, error=error), 400

    game = GameJournal(**game_values(draft))
    db.session.add(game)
    db.session.commit()
    return redirect_to_games(game.id)


@games_bp.post("/<int:game_id>")
def update(game_id):
    game = db.get_or_404(GameJournal, game_id)
    draft, error = game_from_form()
    if error:
        return render_games(selected_game=game, draft=draft, error=error), 400

    for field, value in game_values(draft).items():
        setattr(game, field, value)
    db.session.commit()
    return redirect_to_games(game.id)


@games_bp.post("/<int:game_id>/delete")
def delete(game_id):
    game = db.get_or_404(GameJournal, game_id)
    db.session.delete(game)
    db.session.commit()
    return redirect_to_games()


def render_games(new_game=False, selected_game=None, draft=None, error=None):
    if new_game and draft is None:
        draft = GameDraft()
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

    if selected_game is None and not new_game and games:
        selected_id = request.args.get("game_id", type=int)
        selected_game = next((game for game in games if game.id == selected_id), games[0])

    return render_template(
        "games/index.html",
        games=games,
        selected_game=selected_game,
        new_game=new_game,
        draft=draft,
        error=error,
        query=query,
        status=status,
        statuses=VALID_STATUSES,
    )


def game_from_form():
    draft = GameDraft(
        title=(request.form.get("title") or "").strip(),
        status=request.form.get("status") or "",
        rating=(request.form.get("rating") or "").strip(),
        platform=(request.form.get("platform") or "").strip(),
        hours_played=(request.form.get("hours_played") or "").strip(),
        notes=request.form.get("notes") or "",
    )
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
