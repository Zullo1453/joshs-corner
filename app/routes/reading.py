from flask import Blueprint

from . import section_placeholder
reading_bp = Blueprint("reading", __name__, url_prefix="/reading")


@reading_bp.get("/")
def index():
    return section_placeholder("Reading List")
