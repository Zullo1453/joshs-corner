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

## Database changes

Use Flask-Migrate for every schema change. Before applying future migrations,
create a database backup. The automated backup and restore workflow will be
added in Stage 2D.

## Restore

The full backup and restore procedure will be added with the Stage 2D backup
scripts. Never overwrite `instance\joshs_corner.db` while the application is
running.
