from datetime import date

from flask import Blueprint, current_app, render_template

from ..daily_thought import DailyThoughtService
from ..deadlines import active_deadlines, status_for
from ..upcoming import upcoming_events, status_for as upcoming_status

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
    try:
        daily_thought = DailyThoughtService().get_thought(today)
    except ValueError:
        daily_thought = None
    return render_template(
        "home.html", today=today, historical_event=historical_event, daily_figure=daily_figure,
        daily_thought=daily_thought, upcoming_deadlines=active_deadlines(3), deadline_status=status_for,
        upcoming_events=upcoming_events(3), upcoming_status=upcoming_status,
    )


def current_date():
    return date.today()
