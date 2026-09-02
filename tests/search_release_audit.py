"""Read-only release checks; generated snapshots stay under ignored instance/."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from app.backup import validate_backup_package
from app.extensions import db
from app import models  # populate metadata without starting the application

parser = argparse.ArgumentParser()
parser.add_argument("--baseline", action="store_true")
args = parser.parse_args()
database = ROOT / "instance" / "joshs_corner.db"
uri = database.as_uri() + "?mode=ro"
with sqlite3.connect(uri, uri=True) as connection:
    schema = list(connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"))
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
    revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    table_counts = {name: connection.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0]
                    for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
snapshot = {
    "database_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
    "schema_sha256": hashlib.sha256(json.dumps(schema).encode()).hexdigest(),
    "counts": table_counts,
}
baseline = ROOT / "instance" / "search-release-baseline.json"
if args.baseline:
    baseline.write_text(json.dumps(snapshot), encoding="utf-8")
else:
    assert snapshot == json.loads(baseline.read_text()), "Live database changed since baseline"
engine = create_engine("sqlite+pysqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
with engine.connect() as connection:
    schema_diff = compare_metadata(MigrationContext.configure(connection), db.metadata)
engine.dispose()
config = Config()
config.set_main_option("script_location", str(ROOT / "migrations"))
head = ScriptDirectory.from_config(config).get_current_head()
backups = {}
for category in ("rolling", "monthly"):
    files = sorted((ROOT / "backups" / category).glob("*.zip"), key=lambda item: item.stat().st_mtime)
    latest = files[-1]
    validate_backup_package(latest)
    backups[category] = {"latest": latest.name, "validated": True}
assert integrity == "ok" and not foreign_keys
assert revision == head
assert not schema_diff, repr(schema_diff)
print(json.dumps({
    "baseline": args.baseline, "integrity": integrity, "foreign_key_violations": len(foreign_keys),
    "migration_head": head, "schema_differences": len(schema_diff),
    "database_unchanged": None if args.baseline else True, "backups": backups,
}))
