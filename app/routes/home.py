from datetime import date

from flask import Blueprint, render_template
from sqlalchemy import extract

from ..models import JournalEntry

home_bp = Blueprint("home", __name__)


@home_bp.get("/")
def index():
    today = current_date()
    historical_entries = (
        JournalEntry.query.filter(
            extract("month", JournalEntry.entry_date) == today.month,
            extract("day", JournalEntry.entry_date) == today.day,
            extract("year", JournalEntry.entry_date) < today.year,
        )
        .order_by(JournalEntry.entry_date.desc())
        .all()
    )
    return render_template("home.html", today=today, historical_entries=historical_entries)


def current_date():
    return date.today()
