"""Read-only, bounded universal search over the existing SQLite tables.

No index, triggers, cached records, ownership assumptions, or persistent queries.
A request-local SQLite function provides Unicode/plain-text matching in SQL.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
import re
import unicodedata

from flask import current_app, url_for
from sqlalchemy import and_, case, func, literal, select
from sqlalchemy.exc import SQLAlchemyError

from .extensions import db
from .models import (
    Deadline, Exercise, GameJournal, GamePlayEntry, JournalEntry, Note, Project,
    ReadingItem, RecurrenceRule, Todo, UpcomingEvent, WatchlistItem, RunRoute,
)
from .note_content import rich_text_preview

MAX_QUERY_LENGTH = 200
RESULT_LIMIT = 40


def normalize_query(value):
    return re.sub(r"[\W_]+", " ", unicodedata.normalize("NFKC", value or "").casefold()).strip()


def plain_text(value, rich=False):
    value = str(value or "")
    if rich:
        value = rich_text_preview(value, limit=2 * len(value) + 1)
    return " ".join(value.split())


def matching_snippet(value, query, limit=160):
    """Clip near a matching word without introducing markup."""
    text = plain_text(value)
    if len(text) <= limit:
        return text
    terms = normalize_query(query).split()
    # Locate words in the original text; casefold can change string length.
    matches = [match.start() for match in re.finditer(r"\w+", text)
               if any(term in normalize_query(match.group()) for term in terms)]
    start = max(0, (min(matches) if matches else 0) - 45)
    end = min(len(text), start + limit - 2)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


@dataclass(frozen=True)
class SearchResult:
    result_type: str
    record_id: int
    title: str
    subtitle: str
    snippet: str
    status: str
    score: int
    destination_url: str
    date: str = ""
    recency: str = ""

    def public(self):
        # Ranking and database identity stay internal.
        return {key: getattr(self, key) for key in (
            "result_type", "title", "subtitle", "snippet", "status", "destination_url", "date",
        )}


@dataclass(frozen=True)
class Source:
    kind: str
    model: object
    title: object
    fields: tuple = ()
    rich_fields: tuple = ()


SOURCES = (
    Source("Journal", JournalEntry, JournalEntry.entry_date, (), ("body",)),
    Source("Note", Note, Note.title, (), ("body",)),
    Source("To-Do", Todo, Todo.text, (), ("notes",)),
    Source("Recurring", RecurrenceRule, RecurrenceRule.text),
    Source("Project", Project, Project.title, ("description",)),
    Source("Deadline", Deadline, Deadline.title, ("description",)),
    Source("Upcoming", UpcomingEvent, UpcomingEvent.title, ("description",)),
    Source("Game", GameJournal, GameJournal.title, ("platform",), ("notes",)),
    Source("Play log", GamePlayEntry, GameJournal.title, ("title",), ("body",)),
    Source("Watchlist", WatchlistItem, WatchlistItem.title, ("genre", "media_type", "recommendation_note"), ("notes",)),
    Source("Reading", ReadingItem, ReadingItem.title, ("format", "book_type"), ("notes",)),
    Source("Exercise", Exercise, Exercise.name, ("body_part",)),
    Source("Run route", RunRoute, RunRoute.name),
)


class SearchQueryAdapter:
    """Internal boundary for database-specific universal search SQL."""

    @contextmanager
    def connection(self):
        raise NotImplementedError
        yield

    def statement(self, service, source, query, terms):
        raise NotImplementedError


class SQLiteSearchAdapter(SearchQueryAdapter):
    """SQLite custom functions and candidate ranking used by local Search."""

    @contextmanager
    def connection(self):
        with db.engine.connect() as connection:
            if connection.dialect.name != "sqlite":
                raise RuntimeError("SQLite universal search cannot run on this database dialect.")

            @lru_cache(maxsize=2048)
            def text_for_sql(value, rich):
                return normalize_query(plain_text(value, bool(rich)))

            raw = connection.connection.driver_connection
            raw.create_function("jc_search_text", 2, text_for_sql, deterministic=True)
            raw.create_function("jc_search_date", 1, lambda value: (
                f"{value} {date.fromisoformat(value).strftime('%A %d %B %Y %d %b %Y %d/%m/%Y')}"
            ), deterministic=True)
            try:
                yield connection
            finally:
                raw.create_function("jc_search_text", 2, None)
                raw.create_function("jc_search_date", 1, None)
                text_for_sql.cache_clear()

    def statement(self, service, source, query, terms):
        model = source.model
        title = func.jc_search_text(func.jc_search_date(source.title) if source.kind == "Journal" else source.title, 0)
        body = literal("")
        for name in source.fields + source.rich_fields:
            body = body + literal(" ") + func.jc_search_text(getattr(model, name), int(name in source.rich_fields))
        combined = title + literal(" ") + body
        contains = lambda text, value: func.instr(text, value) > 0
        score = case(
            (title == query, 600),
            (func.substr(title, 1, len(query)) == query, 500),
            (contains(title, query), 400),
            (and_(*(contains(title, term) for term in terms)), 300),
            (contains(body, query), 200),
            (and_(*(contains(combined, term) for term in terms)), 100),
            else_=0,
        )
        statement = select(model.__table__, score.label("search_score")).where(score > 0)
        if source.kind == "Play log":
            statement = statement.join(GameJournal, GameJournal.id == model.game_id).add_columns(
                GameJournal.title.label("game_title"), GameJournal.status.label("game_status"),
            )
        # Future authenticated owner filtering remains centralized here.
        statement = service.scope_statement(statement, source)
        if source.kind == "Play log":
            ranked = statement.add_columns(func.row_number().over(
                partition_by=model.game_id, order_by=(score.desc(), model.updated_at.desc(), model.id),
            ).label("game_rank")).subquery()
            return select(ranked).where(ranked.c.game_rank == 1).order_by(
                ranked.c.search_score.desc(), ranked.c.updated_at.desc(), ranked.c.id,
            ).limit(RESULT_LIMIT)
        return statement.order_by(score.desc(), model.updated_at.desc(), model.id).limit(RESULT_LIMIT)


class UniversalSearchService:
    def search(self, query):
        if not isinstance(query, str) or len(query) > MAX_QUERY_LENGTH:
            raise ValueError("Search queries must contain at most 200 characters.")
        normalized = normalize_query(query)
        if len(normalized) < 2:
            return [], []
        terms = tuple(dict.fromkeys(normalized.split()))
        results, unavailable = [], []

        # A separate connection prevents autoflush and stale ORM objects. The
        # adapter keeps SQLite-only functions out of the portable service layer.
        adapter = self._adapter()
        with adapter.connection() as connection:
            for source in SOURCES:
                try:
                    rows = connection.execute(self._statement(source, normalized, terms)).mappings().all()
                    results.extend(self._result(source, row, query) for row in rows)
                except SQLAlchemyError as error:
                    if current_app.testing:
                        raise
                    unavailable.append(source.kind)
                    # Exception messages can contain SQL parameters. Never log them.
                    current_app.logger.error("Universal search source %s unavailable (%s)", source.kind, type(error).__name__)
        results.sort(key=lambda item: (-item.score, item.result_type, item.record_id))
        results.sort(key=lambda item: item.recency, reverse=True)
        results.sort(key=lambda item: -item.score)
        # Multiple play entries and a matching review produce one useful game.
        unique = {}
        for result in results:
            unique.setdefault((result.result_type, result.record_id), result)
        return list(unique.values())[:RESULT_LIMIT], unavailable

    def scope_statement(self, statement, source):
        """Central hook for future owner filtering; never client-selected tables."""
        return statement

    def _adapter(self):
        if db.engine.dialect.name == "sqlite":
            return SQLiteSearchAdapter()
        raise RuntimeError("Universal Search has no adapter for the active database dialect.")

    def _statement(self, source, query, terms):
        # Kept as a seam for source-level failure handling and focused tests.
        return self._adapter().statement(self, source, query, terms)

    def _result(self, source, row, query):
        kind, model = source.kind, source.model
        identifier = row["id"]
        title = str(row.get(source.title.key, ""))
        body = " ".join(plain_text(row[name], name in source.rich_fields) for name in source.fields + source.rich_fields)
        status, when = "", None
        today = current_app.config.get("SEARCH_TODAY") or date.today()
        if kind == "Journal":
            when = row["entry_date"]
            title = f"{when.day} {when.strftime('%B %Y')}"
            url = url_for("journal.entry", entry_date=when.isoformat())
        elif kind == "Note":
            url = url_for("notes.index", note_id=identifier)
        elif kind == "To-Do":
            status = row["status"].title()
            if status == "Active":
                status = "Backlog" if row["current_location"] == "backlog" else "Scheduled" if row["scheduled_date"] and row["scheduled_date"] > today else "Active"
            if row["carry_count"]:
                status += " · Carried forward"
            when = row["scheduled_date"]
            url = url_for("todos.task_detail", todo_id=identifier)
        elif kind == "Recurring":
            kind = "To-Do"
            status = "Recurring" if row["is_active"] else "Recurring · Stopped"
            from json import loads
            unit = {"daily": "day", "weekly": "week", "monthly": "month"}[row["recurrence_type"]]
            body = f"Every {row['interval']} {unit}{'s' if row['interval'] != 1 else ''}"
            if unit == "week":
                body += " · " + ", ".join(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[i] for i in loads(row["weekdays_json"]))
            if unit == "month":
                body += f" · day {row['day_of_month']}"
            # IDs may coincide with regular tasks; use a distinct result type.
            kind = "Recurring To-Do"
            when = row["start_date"]
            url = url_for("todos.recurring", _anchor=f"recurrence-{identifier}")
        elif kind == "Project":
            status = row["status"].title()
            url = url_for("todos.project_detail", project_id=identifier)
        elif kind == "Deadline":
            status = "Completed" if row["is_completed"] else "Active"
            when = row["due_date"]
            url = url_for("deadlines.detail", deadline_id=identifier)
        elif kind == "Upcoming":
            when = row["event_date"]
            status = "Past" if when < today else "Upcoming"
            url = url_for("upcoming.detail", event_id=identifier)
        elif kind in {"Game", "Play log"}:
            if kind == "Play log":
                identifier, title = row["game_id"], row["game_title"]
                status = row["game_status"] + " · Play log"
                when = row["played_on"]
            else:
                status = row["status"]
            url = url_for("games.index", game_id=identifier, _anchor="play-log-title" if kind == "Play log" else None)
            kind = "Game"
        elif kind == "Watchlist":
            status = row["status"]
            url = url_for("watchlist.index", item_id=identifier)
        elif kind == "Reading":
            status = row["status"]
            url = url_for("reading.index", book_id=identifier)
        elif kind == "Run route":
            url = url_for("exercise.route_detail", route_id=identifier)
            kind = "Exercise · Run route"
        else:
            status = "" if row["active"] else "Archived"
            url = url_for("gym.exercise_detail", exercise_id=identifier)
        subtitle = " · ".join(part for part in (kind, status, when.isoformat() if when else "", row.get("body_part", "")) if part)
        return SearchResult(kind, identifier, title, subtitle, matching_snippet(body, query), status,
                            row["search_score"], url, when.isoformat() if when else "", row["updated_at"].isoformat())
