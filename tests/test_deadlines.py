from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flask_migrate import downgrade, upgrade

from app.deadlines import active_deadlines, status_for
from app.extensions import db
from app.models import Deadline


def create_deadline(title, due_date, completed=False, completed_at=None, description=""):
    item = Deadline(
        title=title, due_date=due_date, description=description, is_completed=completed,
        completed_at=completed_at,
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_calendar_day_statuses_are_injectable_and_handle_boundaries():
    current = date(2026, 8, 19)
    assert status_for(date(2026, 8, 25), current)["label"] == "6 days left"
    assert status_for(date(2026, 8, 20), current)["label"] == "1 day left"
    assert status_for(date(2026, 8, 19), current)["label"] == "Due today"
    assert status_for(date(2026, 8, 18), current)["label"] == "1 day overdue"
    assert status_for(date(2026, 8, 15), current)["label"] == "4 days overdue"
    assert status_for(date(2027, 1, 1), date(2026, 12, 31))["label"] == "1 day left"
    assert status_for(date(2024, 2, 29), date(2024, 2, 28))["label"] == "1 day left"


def test_home_shows_active_deadlines_in_urgent_order_until_the_preview_height_is_full(app, client):
    with app.app_context():
        today = date.today()
        overdue = create_deadline("Overdue", today - timedelta(days=1))
        due_today = create_deadline("Today", today)
        soon = create_deadline("Soon", today + timedelta(days=2))
        later = create_deadline("Later", today + timedelta(days=5))
        much_later = create_deadline("Much later", today + timedelta(days=10))
        create_deadline("Completed", today - timedelta(days=2), completed=True, completed_at=datetime.now(timezone.utc))
        assert [item.id for item in active_deadlines()] == [overdue.id, due_today.id, soon.id, later.id, much_later.id]
    page = client.get("/")
    assert page.data.count(b'class="tile"') == 6
    assert b"Upcoming Deadlines" in page.data
    assert b"Overdue" in page.data and b"Due today" in page.data and b"Soon" in page.data and b"Later" in page.data
    assert b"Much later" in page.data and b"Completed" not in page.data
    assert page.data.index(b"Overdue") < page.data.index(b"Today") < page.data.index(b"Soon") < page.data.index(b"Later")
    with app.app_context():
        db.session.get(Deadline, overdue.id).is_completed = True
        db.session.get(Deadline, overdue.id).completed_at = datetime.now(timezone.utc)
        db.session.commit()
        assert [item.title for item in active_deadlines(3)] == ["Today", "Soon", "Later"]


def test_deadline_crud_detail_and_completion_flow(app, client):
    response = client.post("/deadlines", data={"title": "  Application  ", "description": "A <careful> note", "due_date": "2026-08-30"})
    assert response.status_code == 302
    with app.app_context():
        item = db.session.scalar(db.select(Deadline))
        deadline_id = item.id
        assert (item.title, item.description) == ("Application", "A <careful> note")
    detail = client.get(f"/deadlines/{deadline_id}")
    assert detail.status_code == 200
    assert b"A &lt;careful&gt; note" in detail.data
    client.post(f"/deadlines/{deadline_id}/edit", data={"title": "Updated", "description": "Long description", "due_date": "2026-08-18"})
    with app.app_context():
        item = db.session.get(Deadline, deadline_id)
        assert (item.title, item.due_date) == ("Updated", date(2026, 8, 18))
    client.post(f"/deadlines/{deadline_id}/complete")
    with app.app_context():
        item = db.session.get(Deadline, deadline_id)
        assert item.is_completed and item.completed_at is not None
    assert b"Completed" in client.get("/deadlines").data
    client.post(f"/deadlines/{deadline_id}/reopen")
    with app.app_context():
        item = db.session.get(Deadline, deadline_id)
        assert not item.is_completed and item.completed_at is None
    client.post(f"/deadlines/{deadline_id}/delete")
    with app.app_context():
        assert db.session.get(Deadline, deadline_id) is None


def test_deadline_validation_invalid_ids_and_gets_do_not_mutate(app, client):
    assert b"Enter a deadline title" in client.post("/deadlines", data={"title": " ", "due_date": "2026-08-20"}, follow_redirects=True).data
    assert b"Choose a valid due date" in client.post("/deadlines", data={"title": "Missing date", "due_date": ""}, follow_redirects=True).data
    assert client.get("/deadlines/999").status_code == 404
    assert client.post("/deadlines/999/complete").status_code == 404
    with app.app_context():
        item = create_deadline("Untouched", date(2026, 8, 20))
        item_id = item.id
    assert client.get(f"/deadlines/{item_id}").status_code == 200
    with app.app_context():
        assert db.session.get(Deadline, item_id).is_completed is False


def test_deadline_posts_have_csrf_protection():
    from app import create_app

    secure = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "WTF_CSRF_ENABLED": True})
    with secure.app_context():
        db.create_all()
    client = secure.test_client()
    assert client.post("/deadlines", data={"title": "Blocked", "due_date": "2026-08-20"}).status_code == 400
    assert client.post("/deadlines/1/complete").status_code == 400
    with secure.app_context():
        db.drop_all()


def test_deadline_migration_upgrades_downgrades_and_reupgrades(tmp_path):
    from app import create_app

    database = tmp_path / "deadline-migration.db"
    migration_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with migration_app.app_context():
        upgrade(directory=str(migrations), revision="c4a1e8d9f320")
        upgrade(directory=str(migrations), revision="head")
        assert "deadline" in db.inspect(db.engine).get_table_names()
        downgrade(directory=str(migrations), revision="c4a1e8d9f320")
        assert "deadline" not in db.inspect(db.engine).get_table_names()
        upgrade(directory=str(migrations), revision="head")
        assert "deadline" in db.inspect(db.engine).get_table_names()
