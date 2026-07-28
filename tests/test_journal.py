from datetime import date
from pathlib import Path
import hashlib

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import JournalEntry


def test_calendar_page_loads_with_correct_leap_month(client):
    response = client.get("/journal/?year=2024&month=2")

    assert response.status_code == 200
    assert b"February 2024" in response.data
    assert b'data-date="2024-02-29"' in response.data
    assert b'data-date="2024-01-29"' in response.data
    assert b'data-date="2024-03-03"' in response.data
    assert b"/journal/?year=2024&amp;month=1" in response.data
    assert b"/journal/?year=2024&amp;month=3" in response.data


def test_calendar_marks_today(client, monkeypatch):
    from app.routes import journal

    monkeypatch.setattr(journal, "current_date", lambda: date(2026, 7, 28))
    response = client.get("/journal/?year=2026&month=7")

    assert attribute_for(response.data, "2026-07-28", b"today")
    assert b'aria-current="date"' in anchor_for(response.data, "2026-07-28")


def test_opening_an_empty_date_shows_blank_new_entry(client):
    response = client.get("/journal/entry/2026-07-12?return_year=2026&return_month=7")

    assert response.status_code == 200
    assert b"12 July 2026" in response.data
    assert b"New journal entry" in response.data
    assert b"Not saved yet" in response.data
    assert b'value=' not in response.data.split(b'id="journal-body"', 1)[1].split(b"</textarea>", 1)[0]
    assert b"/journal/?year=2026&amp;month=7" in response.data


def test_invalid_dates_and_months_are_rejected(client):
    assert client.get("/journal/entry/2026-02-30").status_code == 404
    assert client.get("/journal/?year=2026&month=13").status_code == 404
    assert client.get("/journal/?year=not-a-year&month=7").status_code == 404


def test_create_and_update_entry(client, app):
    create_response = client.post(
        "/journal/entry/2026-07-12?return_year=2026&return_month=7",
        data={"body": "A new journal entry."},
        follow_redirects=True,
    )
    assert create_response.status_code == 200
    assert b"A new journal entry." in create_response.data
    assert b"Last saved" in create_response.data

    update_response = client.post(
        "/journal/entry/2026-07-12",
        data={"body": "The updated journal entry."},
        follow_redirects=True,
    )
    assert update_response.status_code == 200
    assert b"The updated journal entry." in update_response.data

    with app.app_context():
        entries = db.session.execute(
            db.select(JournalEntry).where(JournalEntry.entry_date == date(2026, 7, 12))
        ).scalars().all()
        assert len(entries) == 1
        assert entries[0].body == "The updated journal entry."


def test_model_prevents_duplicate_entries_for_one_date(app):
    with app.app_context():
        db.session.add_all(
            [
                JournalEntry(entry_date=date(2026, 7, 13), body="First"),
                JournalEntry(entry_date=date(2026, 7, 13), body="Second"),
            ]
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_delete_removes_entry_and_calendar_marker(client, app):
    with app.app_context():
        db.session.add(JournalEntry(entry_date=date(2026, 7, 14), body="Delete me"))
        db.session.commit()

    marked = client.get("/journal/?year=2026&month=7")
    assert attribute_for(marked.data, "2026-07-14", b"has-entry")

    deleted = client.post(
        "/journal/entry/2026-07-14/delete",
        data={"return_year": "2026", "return_month": "7"},
        follow_redirects=True,
    )
    assert deleted.status_code == 200
    assert not attribute_for(deleted.data, "2026-07-14", b"has-entry")

    with app.app_context():
        assert JournalEntry.query.filter_by(entry_date=date(2026, 7, 14)).count() == 0


def test_calendar_entry_marker_and_preview(client, app):
    with app.app_context():
        db.session.add(JournalEntry(entry_date=date(2026, 8, 3), body="Marked day"))
        db.session.commit()

    response = client.get("/journal/?year=2026&month=8")

    assert attribute_for(response.data, "2026-08-03", b"has-entry")
    assert b'data-has-entry="true"' in anchor_for(response.data, "2026-08-03")
    assert b"Marked day" in response.data


def test_on_this_day_matches_previous_years_only(client, app, monkeypatch):
    from app.routes import home

    monkeypatch.setattr(home, "current_date", lambda: date(2026, 7, 28))
    with app.app_context():
        db.session.add_all(
            [
                JournalEntry(entry_date=date(2025, 7, 28), body="Matching history"),
                JournalEntry(entry_date=date(2026, 7, 28), body="Today should not appear"),
                JournalEntry(entry_date=date(2024, 7, 27), body="Wrong day"),
                JournalEntry(entry_date=date(2027, 7, 28), body="Future should not appear"),
            ]
        )
        db.session.commit()

    response = client.get("/")

    assert b"Matching history" in response.data
    assert b"Today should not appear" not in response.data
    assert b"Wrong day" not in response.data
    assert b"Future should not appear" not in response.data
    assert b"/journal/entry/2025-07-28" in response.data


def test_on_this_day_empty_state(client, monkeypatch):
    from app.routes import home

    monkeypatch.setattr(home, "current_date", lambda: date(2026, 7, 28))
    response = client.get("/")

    assert b"Past journal entries from this date will appear here." in response.data


def test_all_prototypes_remain_unchanged():
    project_root = Path(__file__).resolve().parents[1]
    expected_hashes = {
        "Game Journal Prototype.html": "BC1D80F599FB14E3F732407F513B9626F993EA13CF6054588A6567CD9A2E822B",
        "General Notes Prototype.html": "8B715522451B39D28B87EE83B9212C3827D42DA5F579E2C098A98B85446214B2",
        "Homepage Prototype.html": "3E15D18CE9D90BDACC8527532F61CE2B08EC3D2B8C6A832BB6595DB0DE6AA53F",
        "Journal Calender Prototype.html": "0B6AFA39F305B2CB23D787243BAF3B62447CBB68A66CECAD39AD3FB06EAF8C3D",
        "Journal Entry Prototype.html": "235E40049183950F1E60ADCCDE9EB71A0963BAEE068AE602F03BA25D96EE4709",
        "Reading List Prototype.html": "6D6C60EECF2EBA1150C38AAC42C583169F0A18CC7CEE34E95CDD5C710573C581",
        "To Dos Prototype.html": "A0E419EE965AD7B28C406A1223EA564462E8EBE6741299ABA47F9ACBFB1926FE",
        "Watchlist Prototype.html": "8BD0CFC5873152C34640880376BA6ACD3A33325A5A568CF25B83449543A5AEAF",
    }

    prototype_files = {path.name for path in (project_root / "Prototypes").iterdir() if path.is_file()}
    assert prototype_files == set(expected_hashes)
    for filename, expected_hash in expected_hashes.items():
        contents = (project_root / "Prototypes" / filename).read_bytes()
        assert hashlib.sha256(contents).hexdigest().upper() == expected_hash


def anchor_for(page, iso_date):
    attribute_position = page.index(f'data-date="{iso_date}"'.encode())
    anchor_start = page.rindex(b"<a", 0, attribute_position)
    anchor_end = page.index(b">", attribute_position) + 1
    return page[anchor_start:anchor_end]


def attribute_for(page, iso_date, attribute):
    return attribute in anchor_for(page, iso_date)
