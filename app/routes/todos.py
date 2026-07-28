from flask import Blueprint

from . import section_placeholder
todos_bp = Blueprint("todos", __name__, url_prefix="/todos")


@todos_bp.get("/")
def index():
    return section_placeholder("To-Dos")
