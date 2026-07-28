from flask import Blueprint

from . import section_placeholder
watchlist_bp = Blueprint("watchlist", __name__, url_prefix="/watchlist")


@watchlist_bp.get("/")
def index():
    return section_placeholder("Watchlist")
