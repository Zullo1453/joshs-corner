"""Read-only local storage and record-count summaries for Intelligence → Usage."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from .attachments import configured_upload_root
from .extensions import db
from .models import Deadline, Exercise, ExerciseSet, GameJournal, JournalEntry, Note, Project, ReadingItem, Run, RunRoute, Todo, UpcomingEvent, WatchlistItem, WorkoutSession, WorkoutTemplate


UNITS = ("KB", "MB", "GB")
COUNT_MODELS = (
    ("Journal entries", JournalEntry), ("General notes", Note), ("To-Dos", Todo), ("Projects", Project),
    ("Deadlines", Deadline), ("Upcoming events", UpcomingEvent), ("Game Journal entries", GameJournal),
    ("Watchlist items", WatchlistItem), ("Reading List items", ReadingItem), ("Exercises", Exercise),
    ("Strength workouts", WorkoutSession), ("Exercise sets", ExerciseSet), ("Runs", Run),
    ("Run routes", RunRoute), ("Workout templates", WorkoutTemplate),
)


def format_bytes(value: int) -> str:
    """Return a compact, path-free size label using KB, MB, or GB."""
    amount, unit = max(0, int(value)) / 1024, "KB"
    for candidate in UNITS[1:]:
        if amount < 1024:
            break
        amount, unit = amount / 1024, candidate
    return f"{amount:,.1f}".rstrip("0").rstrip(".") + f" {unit}"


def _directory_usage(directory: Path) -> dict:
    if not directory.is_dir():
        return {"bytes": 0, "count": 0}
    files = [item for item in directory.rglob("*") if item.is_file()]
    return {"bytes": sum(item.stat().st_size for item in files), "count": len(files)}


class UsageService:
    """Local-only usage collector; cloud providers can be added independently later."""

    def __init__(self, app, *, database_path: Path | None = None, upload_directory: Path | None = None, backup_root: Path | None = None):
        self.app, self._database_path = app, database_path
        self._upload_directory, self._backup_root = upload_directory, backup_root

    def _database_file(self) -> Path | None:
        if self._database_path is not None:
            return self._database_path
        url = db.engine.url
        if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
            return None
        return Path(url.database)

    def _backup_usage(self) -> dict:
        root = self._backup_root or Path(self.app.root_path).parent / "backups"
        rolling, monthly = _directory_usage(root / "rolling"), _directory_usage(root / "monthly")
        legacy = [item for item in root.glob("joshs_corner_*") if item.is_file()] if root.is_dir() else []
        return {"bytes": rolling["bytes"] + monthly["bytes"] + sum(item.stat().st_size for item in legacy),
                "count": rolling["count"] + monthly["count"] + len(legacy), "rolling": rolling, "monthly": monthly}

    def local_usage(self) -> dict:
        database = self._database_file()
        database_bytes = database.stat().st_size if database and database.is_file() else 0
        uploads, backups = _directory_usage(self._upload_directory or configured_upload_root(self.app)), self._backup_usage()
        total = database_bytes + uploads["bytes"] + backups["bytes"]
        return {"database": {"bytes": database_bytes, "label": format_bytes(database_bytes)},
                "uploads": {**uploads, "label": format_bytes(uploads["bytes"])},
                "backups": {**backups, "label": format_bytes(backups["bytes"])},
                "total": {"bytes": total, "label": format_bytes(total)}}

    def database_counts(self) -> list[dict]:
        return [{"label": label, "count": db.session.scalar(select(func.count(model.id)))} for label, model in COUNT_MODELS]
