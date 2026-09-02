"""Stage 5A contract tests use only the fixture's isolated database."""
from datetime import date, datetime, timedelta
import logging
import time

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.models import (
    Deadline, Exercise, GameJournal, GamePlayEntry, JournalEntry, Note, Project,
    ReadingItem, RecurrenceRule, TaskOccurrence, Todo, UpcomingEvent, WatchlistItem,
)
from app.search import UniversalSearchService, normalize_query, plain_text, matching_snippet

DAY = date(2026, 9, 2)


def seed_records():
    game = GameJournal(title="Public Economics Game", notes="<p>Public Economics review</p>", platform="PC")
    records = [
        JournalEntry(entry_date=DAY, body="<p>Watch <strong>Public Economics</strong> before class</p>"),
        Note(title="Public Economics Notes", body="<p>Public goods and externalities</p>"),
        Todo(text="Public Economics lecture", notes="<p>Prepare for class</p>", scheduled_date=DAY,
             current_location="dated", carry_count=2),
        RecurrenceRule(text="Public Economics weekly", recurrence_type="weekly", interval=1,
                       weekdays_json="[6]", start_date=DAY),
        Project(title="Public Economics Project", description="Assessment preparation"),
        Deadline(title="Public Economics Exam", description="Practice questions", due_date=DAY),
        UpcomingEvent(title="Public Economics Event", description="Study group", event_date=DAY - timedelta(days=1)),
        game,
        WatchlistItem(title="Public Economics Film", media_type="Movie", genre="Documentary",
                      recommendation_note="Policy debate", notes="<p>Useful examples</p>"),
        ReadingItem(title="Public Economics Book", book_type="non_fiction", notes="<p>Tax policy</p>"),
        Exercise(name="Public Economics Press", body_part="Shoulders"),
    ]
    db.session.add_all(records)
    db.session.flush()
    db.session.add_all([
        GamePlayEntry(game_id=game.id, played_on=DAY, title="First session", body="<p>Public Economics play narrative</p>"),
        GamePlayEntry(game_id=game.id, played_on=DAY, title="Second session", body="<p>Public Economics play narrative</p>"),
    ])
    db.session.commit()
    return records


def search(client, query):
    response = client.post("/search", json={"query": query})
    assert response.status_code == 200, response.data
    return response.json["results"]


@pytest.mark.parametrize("value,expected", [
    ("  Public   ECONOMICS ", "public economics"), ("CBA-GradFest", "cba gradfest"),
    ("CBA GradFest", "cba gradfest"), ("Straße", "strasse"),
    ("CAFÉ", "café"), ("Ｅｃｏｎ", "econ"), ("你好", "你好"), ("%", ""),
])
def test_normalization(value, expected):
    assert normalize_query(value) == expected


@pytest.mark.parametrize("query", ["", " ", "x", " % _ ", "📚"])
def test_short_query_does_no_database_work(client, app, query):
    calls = []
    with app.app_context():
        def capture(*args):
            calls.append(args[2])
        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            assert search(client, query) == []
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)
    assert calls == []


def test_all_supported_modules_exact_targets_and_no_mutation(client, app):
    app.config["SEARCH_TODAY"] = DAY
    with app.app_context():
        seed_records()
        before = list(db.session.execute(select(TaskOccurrence)).scalars())
    result = search(client, "  PUBLIC   economics ")
    assert {item["result_type"] for item in result} == {
        "Journal", "Note", "To-Do", "Recurring To-Do", "Project", "Deadline",
        "Upcoming", "Game", "Watchlist", "Reading", "Gym",
    }
    assert len(result) == 11
    destinations = {
        "Journal": "/journal/entry/2026-09-02", "Note": "/notes/?note_id=1",
        "To-Do": "/todos/task/1", "Recurring To-Do": "/todos/recurring#recurrence-1",
        "Project": "/todos/projects/1", "Deadline": "/deadlines/1",
        "Upcoming": "/upcoming/1", "Game": "/games/?game_id=1",
        "Watchlist": "/watchlist/?item_id=1", "Reading": "/reading/?book_id=1",
        "Gym": "/gym/exercises/1",
    }
    for item in result:
        assert item["destination_url"].split("#")[0] == destinations[item["result_type"]].split("#")[0]
        assert len(item["snippet"]) <= 160
        assert "<p>" not in item["snippet"] and "<strong>" not in item["snippet"]
        page = client.get(item["destination_url"])
        assert page.status_code == 200
        assert item["title"].encode() in page.data
        assert "score" not in item and "record_id" not in item
    assert b'id="recurrence-1"' in client.get("/todos/recurring").data
    with app.app_context():
        assert list(db.session.execute(select(TaskOccurrence)).scalars()) == before


@pytest.mark.parametrize("model,values,query,kind", [
    (Note, dict(title="Alpha", body="<p>Quantum knowledge</p>"), "quantum", "Note"),
    (Todo, dict(text="Alpha", notes="<p>Quantum task notes</p>"), "quantum", "To-Do"),
    (Project, dict(title="Alpha", description="Quantum project"), "quantum", "Project"),
    (Deadline, dict(title="Alpha", description="Quantum assessment", due_date=DAY), "quantum", "Deadline"),
    (UpcomingEvent, dict(title="Alpha", description="Quantum visit", event_date=DAY), "quantum", "Upcoming"),
    (GameJournal, dict(title="Alpha", notes="<p>Quantum review</p>"), "quantum", "Game"),
    (GameJournal, dict(title="Alpha", platform="Console"), "console", "Game"),
    (WatchlistItem, dict(title="Alpha", media_type="Movie", genre="Quantum"), "quantum", "Watchlist"),
    (WatchlistItem, dict(title="Alpha", media_type="Movie", recommendation_note="Quantum"), "quantum", "Watchlist"),
    (WatchlistItem, dict(title="Alpha", media_type="Movie", notes="<p>Quantum review</p>"), "quantum", "Watchlist"),
    (ReadingItem, dict(title="Alpha", notes="<p>Quantum author in notes</p>"), "quantum", "Reading"),
    (Exercise, dict(name="Press", body_part="Shoulders"), "shoulders", "Gym"),
])
def test_supported_secondary_fields(client, app, model, values, query, kind):
    with app.app_context():
        db.session.add(model(**values))
        db.session.commit()
    result = search(client, query)
    assert len(result) == 1 and result[0]["result_type"] == kind


def test_play_entry_only_match_is_grouped_and_links_to_game(client, app):
    with app.app_context():
        game = GameJournal(title="Quiet game")
        db.session.add(game)
        db.session.flush()
        db.session.add_all([GamePlayEntry(game_id=game.id, title="Quantum session", played_on=DAY, body="<p>Hidden narrative</p>") for _ in range(70)])
        db.session.commit()
    result = search(client, "quantum narrative")
    assert len(result) == 1
    assert result[0]["title"] == "Quiet game"
    assert "Play log" in result[0]["status"]
    assert result[0]["destination_url"] == "/games/?game_id=1#play-log-title"


@pytest.mark.parametrize("query", ["2026-09-02", "2 September 2026", "02 Sep 2026", "02/09/2026"])
def test_journal_date_search(client, app, query):
    with app.app_context():
        db.session.add(JournalEntry(entry_date=DAY, body="Date lookup"))
        db.session.commit()
    assert search(client, query)[0]["result_type"] == "Journal"


def test_ranking_is_stable_and_title_priorities_win(client, app):
    rows = [
        Note(title="Public Economics"),
        Note(title="Public Economics class"),
        Note(title="Study Public Economics today"),
        Note(title="Economics and public choices"),
        Note(title="Body phrase", body="<p>Public Economics</p>"),
        Note(title="Body words", body="<p>Public choices affect economics</p>"),
        Note(title="Only public"),
    ]
    expected_titles = [row.title for row in rows[:-1]]
    with app.app_context():
        db.session.add_all(rows)
        db.session.commit()
    actual = search(client, "public economics")
    assert [item["title"] for item in actual] == expected_titles
    assert actual == search(client, "public economics")


@pytest.mark.parametrize("title,query", [("CBA-GradFest", "CBA GradFest"), ("Straße Café", "STRASSE CAFÉ"), ("你好笔记", "你好")])
def test_unicode_and_punctuation_match_in_database(client, app, title, query):
    with app.app_context():
        db.session.add(Note(title=title))
        db.session.commit()
    assert search(client, query)[0]["title"] == title


def test_rich_text_plain_matching_and_attributes_not_searched(client, app):
    body = '<p>Watch <strong>Public</strong> Economics</p><ul><li>Tax &amp; spend</li></ul><blockquote>Policy</blockquote><p><a href="https://private-keyword.invalid">Source words</a></p><img src="/attachments/999" alt="image-secret"><p>&lt;unsafe&gt;</p>'
    with app.app_context():
        db.session.add(Note(title="Rich sample", body=body))
        db.session.commit()
    for query in ("public economics", "tax spend", "policy", "source words"):
        result = search(client, query)
        assert len(result) == 1 and "<strong>" not in result[0]["snippet"]
    for query in ("private keyword", "image secret", "attachments", "blockquote"):
        assert search(client, query) == []
    assert "Tax & spend" in plain_text(body, True)
    long = "Before " * 60 + "quantum conclusion " + "After " * 60
    assert "quantum" in matching_snippet(long, "quantum") and len(matching_snippet(long, "quantum")) <= 160


def test_historical_states_and_hard_deletion(client, app):
    app.config["SEARCH_TODAY"] = DAY
    with app.app_context():
        rows = [
            Todo(text="Quantum done", status="completed", is_completed=True, completed_at=datetime(2026, 9, 1)),
            Todo(text="Quantum archived", status="archived", current_location="archived"),
            Project(title="Quantum project", status="archived"),
            Deadline(title="Quantum deadline", due_date=DAY, is_completed=True),
            UpcomingEvent(title="Quantum past", event_date=DAY - timedelta(days=2)),
            Exercise(name="Quantum press", body_part="Chest", active=False),
            RecurrenceRule(text="Quantum repeat", recurrence_type="daily", start_date=DAY, is_active=False),
            Note(title="Quantum deleted"),
        ]
        db.session.add_all(rows)
        db.session.commit()
        db.session.delete(rows[-1])
        db.session.commit()
    result = search(client, "quantum")
    assert len(result) == 7
    assert {item["status"] for item in result} >= {"Completed", "Archived", "Past", "Recurring · Stopped"}
    for item in result:
        assert client.get(item["destination_url"]).status_code == 200


def test_deleted_result_does_not_survive_next_query(client, app):
    with app.app_context():
        note = Note(title="Quantum")
        db.session.add(note)
        db.session.commit()
        assert search(client, "quantum")
        db.session.delete(note)
        db.session.commit()
        assert search(client, "quantum") == []


def test_transport_is_bounded_private_and_fixed_schema(client):
    assert client.get("/search").status_code == 405
    for payload in ({}, {"query": []}, {"query": "x" * 201}, {"query": "safe", "table": "attachment"}):
        assert client.post("/search", json=payload).status_code == 400
    response = client.post("/search", json={"query": "private sample"})
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert b"private sample" not in response.data
    assert search(client, "%' OR 1=1 --") == []


def test_search_requires_csrf_token(client, app):
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/search", json={"query": "quantum"}).status_code == 400


def test_only_selects_and_bounded_query_count(client, app):
    with app.app_context():
        seed_records()
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            search(client, "public economics")
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)
    assert len(statements) == 12
    assert all(statement.lstrip().startswith("SELECT") for statement in statements)


def test_module_failure_is_visible_without_logging_query(client, app, monkeypatch, caplog):
    with app.app_context():
        seed_records()
    original = UniversalSearchService._statement
    def fail(self, source, query, terms):
        if source.kind == "Note":
            raise OperationalError("SELECT secret", {"query": query}, Exception("secret-private-term"))
        return original(self, source, query, terms)
    monkeypatch.setattr(UniversalSearchService, "_statement", fail)
    app.config["TESTING"] = False
    with caplog.at_level(logging.ERROR):
        response = client.post("/search", json={"query": "public economics"})
    assert response.status_code == 200
    assert response.json["unavailable"] == ["Note"]
    assert response.json["results"]
    assert "public economics" not in caplog.text and "secret-private-term" not in caplog.text
    app.config["TESTING"] = True
    with pytest.raises(OperationalError):
        client.post("/search", json={"query": "public economics"})


def test_global_shell_on_all_starting_modules(client):
    for url in ("/", "/journal/", "/todos/", "/automations", "/gym", "/notes/", "/reading/", "/watchlist/", "/games/"):
        page = client.get(url)
        assert page.status_code == 200
        assert b"data-search-open" in page.data and b"<dialog" in page.data
        assert b'aria-label="Search Josh\'s Corner"' in page.data


def test_larger_dataset_latency_and_global_cap(client, app):
    with app.app_context():
        seed_records()
        start = DAY - timedelta(days=600)
        db.session.add_all([JournalEntry(entry_date=start + timedelta(days=i), body="<p>Public <strong>Economics</strong> journal entry " + str(i) + "</p>") for i in range(500)])
        db.session.add_all([Note(title=f"Lecture {i}", body="<p>Public Economics reference " + str(i) + "</p>") for i in range(500)])
        db.session.add_all([Todo(text=f"Public Economics task {i}") for i in range(500)])
        db.session.commit()
    durations = []
    for query in ("public economics", "lecture", "no matching concept", "public economics", "public economics"):
        start = time.perf_counter()
        result = search(client, query)
        durations.append((time.perf_counter() - start) * 1000)
        assert len(result) <= 40
    print("\nSearch fixture: 1,513 records; latency ms:", [round(value, 1) for value in durations])
    # Generous guard against accidentally quadratic work; timings are reported separately.
    assert max(durations) < 5000
