"""Read-only health diagnostics for the local application."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from .backup import validate_backup_package
from .extensions import db


def _backup_status(directory: Path) -> dict:
    packages = sorted(directory.glob("joshs_corner_backup_*.zip"), key=lambda item: item.stat().st_mtime, reverse=True) if directory.is_dir() else []
    latest = packages[0] if packages else None
    valid = False
    if latest:
        try:
            validate_backup_package(latest)
            valid = True
        except ValueError:
            valid = False
    age = None if not latest else max(0, int((datetime.now().timestamp() - latest.stat().st_mtime) // 86400))
    return {"present": bool(latest), "count": len(packages), "valid": valid, "age_days": age}


def _age_label(age_days: int | None) -> str:
    if age_days is None:
        return "Not available"
    if age_days == 0:
        return "Today"
    if age_days == 1:
        return "1 day ago"
    return f"{age_days} days ago"


def collect_health(app) -> dict:
    """Run non-mutating SQLite, migration, and backup checks; never expose paths."""
    integrity = db.session.execute(text("PRAGMA integrity_check")).scalar() == "ok"
    foreign_keys = list(db.session.execute(text("PRAGMA foreign_key_check")))
    try:
        current = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except OperationalError:
        # Isolated test databases created from models have no migration ledger.
        current = None
    config = Config(str(Path(app.root_path).parent / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(Path(app.root_path).parent / "migrations"))
    expected = ScriptDirectory.from_config(config).get_current_head()
    backup_root = Path(app.root_path).parent / "backups"
    rolling, monthly = _backup_status(backup_root / "rolling"), _backup_status(backup_root / "monthly")
    status = "Healthy"
    message = "All core checks passed."
    if not integrity or foreign_keys or current != expected:
        status, message = "Problem", "A database or migration check needs attention."
    elif not (rolling["present"] and rolling["valid"] and monthly["present"] and monthly["valid"]):
        status, message = "Attention", "A validated backup is not currently available in every local retention set."
    return {
        "status": status, "message": message, "database": {"integrity": integrity, "foreign_keys": not foreign_keys, "migration_current": current == expected},
        "backups": {"rolling": {**rolling, "age_label": _age_label(rolling["age_days"])}, "monthly": {**monthly, "age_label": _age_label(monthly["age_days"])}},
        "local_only": True,
    }
