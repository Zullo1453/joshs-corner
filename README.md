# Josh's Corner

A private, local Windows application built with Flask and SQLite.

## Local setup

The project uses a virtual environment stored in `.venv`.

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m flask --app run.py db upgrade
python run.py
```

Open <http://127.0.0.1:5000>. Press `Ctrl+C` in the terminal to stop the server.

The homepage requests one historical event from Wikipedia's public “On this
day” events feed. Successful results are cached in
`instance\on_this_day_cache.json`. If the request is unavailable, the matching
cached event is used; without a cache, the homepage shows a quiet offline
fallback while the rest of the application continues normally.

## Tests

```powershell
python -m pytest
```

## Database backups and restore

Create a validated backup at any time:

```powershell
python scripts\backup_database.py
```

Backups are created with SQLite's backup API in `backups\` and are never
overwritten. To schedule a daily Windows Task Scheduler job, use Program/script
`<project-root>\.venv\Scripts\python.exe` and arguments
`scripts\backup_database.py`, with the project as Start in. Set
`JOSHS_CORNER_BACKUP_SECONDARY_DIR` to an optional existing local directory
(such as a OneDrive-synchronised folder) to copy completed, validated backups.

Restore testing defaults to a separate database:

```powershell
python scripts\restore_database.py backups\joshs_corner_YYYY-MM-DD_HHMMSS.db --target restore.test.db
```

Live replacement requires `--replace-live`, creates a fresh safety backup
first, and should only be run after stopping the application. Do not use it to
test a restore.

Retention keeps all backups from the most recent 30 days, then up to 12 weekly
representatives, plus one representative for every older month. The helper
reports deletion candidates; retention deletion should be reviewed before use.

## Database changes

Use Flask-Migrate for every schema change. Before applying future migrations,
create and validate a backup, check migration status, run
`python scripts\migrate_safely.py`, then run integrity and application tests.

## Restore

Never overwrite `instance\joshs_corner.db` while the application is running.
