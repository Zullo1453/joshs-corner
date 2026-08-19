from datetime import date, time, timedelta
from pathlib import Path

from flask_migrate import downgrade, upgrade

from app.extensions import db
from app.models import UpcomingEvent
from app.upcoming import past_events, status_for, upcoming_events


def create_event(title, event_date, event_time=None, description=""):
    event = UpcomingEvent(title=title, event_date=event_date, event_time=event_time, description=description)
    db.session.add(event)
    db.session.commit()
    return event


def test_calendar_day_statuses_are_injectable_and_handle_boundaries():
    current = date(2026, 8, 19)
    assert status_for(date(2026, 8, 19), current)["label"] == "Today"
    assert status_for(date(2026, 8, 20), current)["label"] == "Tomorrow"
    assert status_for(date(2026, 8, 21), current)["label"] == "2 days away"
    assert status_for(date(2026, 8, 28), current)["label"] == "9 days away"
    assert status_for(date(2026, 8, 18), current) is None
    assert status_for(date(2026, 9, 1), date(2026, 8, 31))["label"] == "Tomorrow"
    assert status_for(date(2027, 1, 1), date(2026, 12, 31))["label"] == "Tomorrow"
    assert status_for(date(2024, 2, 29), date(2024, 2, 28))["label"] == "Tomorrow"


def test_active_query_uses_calendar_dates_then_timed_events_then_stable_creation_order(app):
    with app.app_context():
        current = date(2026, 8, 19)
        today = create_event("Today", current)
        six_pm = create_event("Six", current + timedelta(days=1), time(18, 0))
        eight_pm = create_event("Eight", current + timedelta(days=1), time(20, 0))
        untimed = create_event("All day", current + timedelta(days=1))
        later = create_event("Later", current + timedelta(days=2))
        past = create_event("Past", current - timedelta(days=1))

        assert [event.id for event in upcoming_events(current_day=current)] == [
            today.id, six_pm.id, eight_pm.id, untimed.id, later.id,
        ]
        assert [event.id for event in past_events(current_day=current)] == [past.id]


def test_home_shows_three_nearest_events_and_keeps_past_events_out(app, client):
    with app.app_context():
        today = date.today()
        events = [
            create_event("Today event", today, time(18, 0)),
            create_event("Tomorrow event", today + timedelta(days=1)),
            create_event("Five-day event", today + timedelta(days=5)),
            create_event("Ten-day event", today + timedelta(days=10)),
            create_event("Twenty-day event", today + timedelta(days=20)),
            create_event("Yesterday event", today - timedelta(days=1)),
        ]
        assert [event.id for event in upcoming_events(3)] == [event.id for event in events[:3]]

    page = client.get("/")
    assert page.status_code == 200
    assert page.data.count(b'class="tile"') == 6
    assert b"Upcoming Deadlines" in page.data
    assert b">Upcoming<" in page.data
    assert b"Today event" in page.data
    assert b"6:00 PM" in page.data
    assert b"Tomorrow event" in page.data
    assert b"Five-day event" in page.data
    assert b"Ten-day event" not in page.data
    assert b"Yesterday event" not in page.data
    assert page.data.index(b"home-deadlines-card") < page.data.index(b"home-upcoming-card")


def test_upcoming_crud_escaping_past_events_invalid_ids_and_get_safety(app, client):
    response = client.post(
        "/upcoming",
        data={"title": "  Grad <Fest>  ", "description": "A <careful> note", "event_date": "2026-08-30", "event_time": "18:00"},
    )
    assert response.status_code == 302
    with app.app_context():
        event = db.session.scalar(db.select(UpcomingEvent))
        event_id = event.id
        assert (event.title, event.description, event.event_time) == ("Grad <Fest>", "A <careful> note", time(18, 0))

    detail = client.get(f"/upcoming/{event_id}")
    assert detail.status_code == 200
    assert b"Grad &lt;Fest&gt;" in detail.data
    assert b"A &lt;careful&gt; note" in detail.data
    assert client.get(f"/upcoming/{event_id}").status_code == 200

    client.post(
        f"/upcoming/{event_id}/edit",
        data={"title": "Updated", "description": "", "event_date": "2026-08-18", "event_time": ""},
    )
    with app.app_context():
        event = db.session.get(UpcomingEvent, event_id)
        assert (event.title, event.event_date, event.event_time) == ("Updated", date(2026, 8, 18), None)
    assert b"Updated" in client.get("/upcoming").data
    assert b"Past" in client.get("/upcoming").data
    assert client.get("/upcoming/999").status_code == 404
    assert client.post("/upcoming/999/delete").status_code == 404

    client.post(f"/upcoming/{event_id}/delete")
    with app.app_context():
        assert db.session.get(UpcomingEvent, event_id) is None


def test_upcoming_validation_and_csrf_protection(app, client):
    assert b"Enter an event title" in client.post(
        "/upcoming", data={"title": " ", "event_date": "2026-08-20"}, follow_redirects=True,
    ).data
    assert b"Choose a valid event date" in client.post(
        "/upcoming", data={"title": "Missing date", "event_date": ""}, follow_redirects=True,
    ).data
    assert b"Choose a valid event time" in client.post(
        "/upcoming", data={"title": "Bad time", "event_date": "2026-08-20", "event_time": "not-time"}, follow_redirects=True,
    ).data

    from app import create_app

    secure = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "WTF_CSRF_ENABLED": True})
    with secure.app_context():
        db.create_all()
    secure_client = secure.test_client()
    assert secure_client.post("/upcoming", data={"title": "Blocked", "event_date": "2026-08-20"}).status_code == 400
    assert secure_client.post("/upcoming/1/delete").status_code == 400
    with secure.app_context():
        db.drop_all()


def test_upcoming_migration_upgrades_downgrades_and_reupgrades(tmp_path):
    from app import create_app

    database = tmp_path / "upcoming-migration.db"
    migration_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with migration_app.app_context():
        upgrade(directory=str(migrations), revision="e8d2c6b1a470")
        upgrade(directory=str(migrations), revision="head")
        assert "upcoming_event" in db.inspect(db.engine).get_table_names()
        downgrade(directory=str(migrations), revision="e8d2c6b1a470")
        assert "upcoming_event" not in db.inspect(db.engine).get_table_names()
        upgrade(directory=str(migrations), revision="head")
        assert "upcoming_event" in db.inspect(db.engine).get_table_names()
