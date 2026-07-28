from datetime import date

from flask import Blueprint, current_app, render_template

home_bp = Blueprint("home", __name__)


@home_bp.get("/")
def index():
    today = current_date()
    try:
        historical_event = current_app.extensions["on_this_day"].get_event(today)
    except Exception:
        historical_event = None
    return render_template("home.html", today=today, historical_event=historical_event)


def current_date():
    return date.today()
