"""Small, explicit boundary for Josh's Corner runtime locations and database URL.

The local application remains file-backed. Keeping these categories together
makes it clear which locations are durable local state and which can be
discarded by a future serverless runtime.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


LOCAL_DATABASE_FILENAME = "joshs_corner.db"


def local_database_uri(instance_path: str | Path) -> str:
    """Return the unchanged local SQLite URL used when no external URL exists."""
    database_path = Path(instance_path) / LOCAL_DATABASE_FILENAME
    return f"sqlite:///{database_path.as_posix()}"


def configured_database_uri(instance_path: str | Path, environ=None) -> str:
    """Select a future external database URL without requiring one locally.

    This function only selects configuration; it deliberately does not open a
    database connection. Stage 1 continues to use SQLite by default.
    """
    environment = os.environ if environ is None else environ
    return environment.get("DATABASE_URL") or local_database_uri(instance_path)


@dataclass(frozen=True)
class RuntimePaths:
    """Classified local paths; no directory is created just by constructing it."""

    project_root: Path
    instance: Path
    local_database: Path
    uploads: Path
    on_this_day_cache: Path
    figure_of_day_cache: Path
    backups: Path
    server_log: Path

    @classmethod
    def for_project(cls, project_root: str | Path) -> "RuntimePaths":
        root = Path(project_root)
        instance = root / "instance"
        return cls(
            project_root=root,
            instance=instance,
            local_database=instance / LOCAL_DATABASE_FILENAME,
            uploads=instance / "uploads",
            on_this_day_cache=instance / "on_this_day_cache.json",
            figure_of_day_cache=instance / "figure_of_day_cache.json",

            backups=root / "backups",
            server_log=instance / "server.log",
        )