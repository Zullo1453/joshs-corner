from datetime import date, time, timedelta
from pathlib import Path

from flask_migrate import downgrade, upgrade

from app.extensions import db
from app.models import Deadline, JournalEntry, UpcomingEvent


def post_entry(client, entry_date, body="Journal note", **values):
    return client.post(f"/journal/entry/{entry_date.isoformat()}", data={"body": body, **values})


def test_journal_form_keeps_both_optional_links_off_by_default(client):
    response = client.get("/journal/entry/2026-09-01")

    assert response.status_code == 200
    assert b"Add to" in response.data
    assert b'name="csrf_token"' in response.data
    assert b'name="link_deadline"' in response.data
    assert b'name="link_upcoming"' in response.data
    assert b"Journal entry \xe2\x80\x94 1 September 2026" in response.data
    assert b'name="link_deadline" value="1" data-link-toggle="deadline" checked' not in response.data
    assert b'data-link-fields="deadline" hidden' in response.data
    assert b'data-link-fields="upcoming" hidden' in response.data
    assert b'name="deadline_due_date" type="date" value="2026-09-01"' in response.data
    assert b'name="upcoming_event_date" type="date" value="2026-09-01"' in response.data
    assert b'data-journal-date="2026-09-01"' in response.data


def test_unlinked_journal_capture_dates_default_to_the_entry_date_and_existing_dates_are_preserved(client, app):
    entry_date = date(2026, 9, 12)
    response = client.get(f"/journal/entry/{entry_date.isoformat()}")
    assert b'name="deadline_due_date" type="date" value="2026-09-12"' in response.data
    assert b'name="upcoming_event_date" type="date" value="2026-09-12"' in response.data

    post_entry(
        client, entry_date, link_deadline="1", deadline_title="Existing deadline", deadline_due_date="2026-10-15",
        link_upcoming="1", upcoming_title="Existing event", upcoming_event_date="2026-10-16",
    )
    response = client.get(f"/journal/entry/{entry_date.isoformat()}")
    assert b'name="deadline_due_date" type="date" value="2026-10-15"' in response.data
    assert b'name="upcoming_event_date" type="date" value="2026-10-16"' in response.data
    with app.app_context():
        entry = db.session.scalar(db.select(JournalEntry))
        assert entry.deadline_link.due_date == date(2026, 10, 15)
        assert entry.upcoming_link.event_date == date(2026, 10, 16)


def test_normal_journal_entry_never_creates_a_deadline_or_event(client, app):
    response = post_entry(
        client, date(2026, 9, 2),
        body="A normal reflection mentioning a date such as 30 September.",
    )

    assert response.status_code == 302
    with app.app_context():
        entry = db.session.scalar(db.select(JournalEntry))
        assert entry.body.startswith("A normal reflection")
        assert entry.deadline_link is None and entry.upcoming_link is None
        assert db.session.scalar(db.select(db.func.count()).select_from(Deadline)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(UpcomingEvent)) == 0


def test_journal_can_create_deadline_upcoming_or_both_and_hub_uses_the_same_records(client, app):
    today = date.today()
    post_entry(
        client, date(2026, 9, 3), link_deadline="1", deadline_title="Registration closes",
        deadline_due_date=(today + timedelta(days=4)).isoformat(),
    )
    post_entry(
        client, date(2026, 9, 4), link_upcoming="1", upcoming_title="GradFest",
        upcoming_event_date=(today + timedelta(days=6)).isoformat(), upcoming_event_time="18:00",
    )
    post_entry(
        client, date(2026, 9, 5), link_deadline="1", deadline_title="Submit form",
        deadline_due_date=(today + timedelta(days=8)).isoformat(), link_upcoming="1",
        upcoming_title="Graduation event", upcoming_event_date=(today + timedelta(days=12)).isoformat(),
    )

    with app.app_context():
        entries = list(db.session.scalars(db.select(JournalEntry).order_by(JournalEntry.entry_date)))
        assert (entries[0].deadline_link is not None, entries[0].upcoming_link is not None) == (True, False)
        assert (entries[1].deadline_link is not None, entries[1].upcoming_link is not None) == (False, True)
        assert (entries[2].deadline_link is not None, entries[2].upcoming_link is not None) == (True, True)
        assert entries[1].upcoming_link.event_time == time(18, 0)
        assert db.session.scalar(db.select(db.func.count()).select_from(Deadline)) == 2
        assert db.session.scalar(db.select(db.func.count()).select_from(UpcomingEvent)) == 2

    hub = client.get("/")
    assert b"Registration closes" in hub.data
    assert b"GradFest" in hub.data
    assert client.get("/deadlines").status_code == 200
    assert client.get("/upcoming").status_code == 200


def test_journal_link_validation_is_transactional_and_does_not_create_partial_records(client, app):
    response = post_entry(client, date(2026, 9, 6), link_deadline="1", deadline_title="Missing date")

    assert response.status_code == 400
    assert b"Choose a valid deadline date" in response.data
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(JournalEntry)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(Deadline)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(UpcomingEvent)) == 0


def test_editing_links_updates_existing_items_without_duplicates_or_overwriting_side_details(client, app):
    entry_date = date(2026, 9, 7)
    post_entry(
        client, entry_date, body="Original", link_deadline="1", deadline_title="Original deadline",
        deadline_due_date="2026-10-01", link_upcoming="1", upcoming_title="Original event",
        upcoming_event_date="2026-10-02", upcoming_event_time="18:00",
    )
    with app.app_context():
        entry = db.session.scalar(db.select(JournalEntry))
        deadline_id, event_id = entry.deadline_link.id, entry.upcoming_link.id
        entry.deadline_link.description = "Deadline details changed in its own Centre"
        entry.upcoming_link.description = "Event details changed in its own page"
        db.session.commit()

    for body in ("Edited body", "Edited body again"):
        response = post_entry(
            client, entry_date, body=body, link_deadline="1", deadline_title="Updated deadline",
            deadline_due_date="2026-10-03", link_upcoming="1", upcoming_title="Updated event",
            upcoming_event_date="2026-10-04", upcoming_event_time="20:30",
        )
        assert response.status_code == 302

    with app.app_context():
        entry = db.session.scalar(db.select(JournalEntry))
        assert entry.body == "Edited body again"
        assert entry.deadline_link.id == deadline_id and entry.upcoming_link.id == event_id
        assert (entry.deadline_link.title, entry.deadline_link.due_date) == ("Updated deadline", date(2026, 10, 3))
        assert (entry.upcoming_link.title, entry.upcoming_link.event_date, entry.upcoming_link.event_time) == (
            "Updated event", date(2026, 10, 4), time(20, 30),
        )
        assert entry.deadline_link.description == "Deadline details changed in its own Centre"
        assert entry.upcoming_link.description == "Event details changed in its own page"
        assert db.session.scalar(db.select(db.func.count()).select_from(Deadline)) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(UpcomingEvent)) == 1


def test_unticking_requires_confirmation_then_deletes_linked_records_while_preserving_journal(client, app):
    entry_date = date(2026, 9, 8)
    post_entry(
        client, entry_date, link_deadline="1", deadline_title="Completed item", deadline_due_date="2026-08-01",
        link_upcoming="1", upcoming_title="Past event", upcoming_event_date="2026-08-02",
    )
    with app.app_context():
        entry = db.session.scalar(db.select(JournalEntry))
        entry.deadline_link.is_completed = True
        db.session.commit()

    blocked = post_entry(client, entry_date, body="Keep journal")
    assert blocked.status_code == 400
    assert b"Confirm removal of the linked Deadline" in blocked.data

    confirmed = post_entry(
        client, entry_date, body="Keep journal", confirm_remove_deadline="1", confirm_remove_upcoming="1",
    )
    assert confirmed.status_code == 302
    with app.app_context():
        entry = db.session.scalar(db.select(JournalEntry))
        assert entry.body == "Keep journal"
        assert entry.deadline_link is None and entry.upcoming_link is None
        assert db.session.scalar(db.select(db.func.count()).select_from(Deadline)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(UpcomingEvent)) == 0


def test_deleting_journal_keeps_linked_records_as_standalone_and_side_deletes_clear_the_relationship(client, app):
    first_date, second_date = date(2026, 9, 9), date(2026, 9, 10)
    post_entry(client, first_date, link_deadline="1", deadline_title="Keep deadline", deadline_due_date="2026-10-10", link_upcoming="1", upcoming_title="Keep event", upcoming_event_date="2026-10-11")
    post_entry(client, second_date, link_deadline="1", deadline_title="Delete from centre", deadline_due_date="2026-10-12", link_upcoming="1", upcoming_title="Delete from upcoming", upcoming_event_date="2026-10-13")
    with app.app_context():
        entries = list(db.session.scalars(db.select(JournalEntry).order_by(JournalEntry.entry_date)))
        retained_deadline_id, retained_event_id = entries[0].deadline_link.id, entries[0].upcoming_link.id
        deleted_deadline_id, deleted_event_id = entries[1].deadline_link.id, entries[1].upcoming_link.id

    assert client.post(f"/journal/entry/{first_date.isoformat()}/delete").status_code == 302
    with app.app_context():
        assert db.session.get(JournalEntry, entries[0].id) is None
        assert db.session.get(Deadline, retained_deadline_id).source_journal_entry_id is None
        assert db.session.get(UpcomingEvent, retained_event_id).source_journal_entry_id is None

    client.post(f"/deadlines/{deleted_deadline_id}/delete")
    client.post(f"/upcoming/{deleted_event_id}/delete")
    with app.app_context():
        entry = db.session.get(JournalEntry, entries[1].id)
        db.session.expire(entry)
        assert entry.deadline_link is None and entry.upcoming_link is None


def test_journal_link_posts_are_csrf_protected_and_migration_round_trips(tmp_path):
    from app import create_app

    secure = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "WTF_CSRF_ENABLED": True})
    with secure.app_context():
        db.create_all()
    assert secure.test_client().post("/journal/entry/2026-09-11", data={"body": "Blocked", "link_deadline": "1"}).status_code == 400
    with secure.app_context():
        db.drop_all()

    database = tmp_path / "journal-link-migration.db"
    migration_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with migration_app.app_context():
        upgrade(directory=str(migrations), revision="f1a4c7d8e520")
        upgrade(directory=str(migrations), revision="head")
        inspector = db.inspect(db.engine)
        assert "source_journal_entry_id" in {column["name"] for column in inspector.get_columns("deadline")}
        assert "source_journal_entry_id" in {column["name"] for column in inspector.get_columns("upcoming_event")}
        downgrade(directory=str(migrations), revision="f1a4c7d8e520")
        assert "source_journal_entry_id" not in {column["name"] for column in db.inspect(db.engine).get_columns("deadline")}
        upgrade(directory=str(migrations), revision="head")
        assert "source_journal_entry_id" in {column["name"] for column in db.inspect(db.engine).get_columns("upcoming_event")}
