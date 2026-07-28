from flask import Blueprint

from . import section_placeholder
games_bp = Blueprint("games", __name__, url_prefix="/games")


@games_bp.get("/")
def index():
    return section_placeholder("Game Journal")
