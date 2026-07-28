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
    try:
        daily_figure = current_app.extensions["figure_of_day"].get_figure(today)
    except Exception:
        daily_figure = None
    return render_template("home.html", today=today, historical_event=historical_event, daily_figure=daily_figure)


def current_date():
    return date.today()
