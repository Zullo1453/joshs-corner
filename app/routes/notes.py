from flask import Blueprint

from . import section_placeholder
notes_bp = Blueprint("notes", __name__, url_prefix="/notes")


@notes_bp.get("/")
def index():
    return section_placeholder("General Notes")
