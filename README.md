# Josh's Corner

A private, local Windows application built with Flask and SQLite. It runs only
on this computer at <http://127.0.0.1:5000>; it does not use GitHub, a cloud
database, or automatic sharing.

## Starting Josh's Corner

For the usual desktop experience, double-click:

```text
Start Josh's Corner.bat
```

It checks the project Python environment, detects an already-running copy,
warns if another application has port 5000, starts the local server, and opens
the browser only after the local page responds. Leave that window open while
using the app; press `Ctrl+C` to stop it.

For a server without opening a browser, use:

```text
Start Josh's Corner - No Browser.bat
```

Neither launcher starts Windows automatically. If you later want the app to
start when you sign in, open **Task Scheduler**, choose **Create Task**, use
**At log on** as the trigger, and choose the normal launcher above as the
action. Create that task only if you want this behaviour.

## Local setup and tests

The project Python environment is stored in `.venv`.

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m flask --app run.py db upgrade
python run.py
python -m pytest
```

The homepage requests one historical event from Wikipedia's public “On this
day” feed. Successful results are cached in
`instance\on_this_day_cache.json`. If the request is unavailable, a matching
cached event is used; without one, the homepage shows a quiet offline fallback
while the rest of the application continues normally.

## Database backups

Backups use SQLite's backup API and are checked with `PRAGMA integrity_check`
before being accepted. The application creates them at startup when due, and
you can also run:

```powershell
.\.venv\Scripts\python.exe scripts\backup_database.py
```

- A rolling backup is made at most once every three days in
  `backups\rolling`; the newest 10 validated rolling backups are kept.
- One validated archive is made per calendar month in `backups\monthly`; the
  newest 12 validated monthly archives are kept.
- Only validated backups in their own rolling or monthly folder are pruned.
  An invalid file is never selected for deletion, and the policy never removes
  the only valid backup in a folder.

The optional secondary destination is configured only in the ignored
`instance\local_config.py` file; its machine-specific location is never
committed to Git.

Only validated monthly archives may be copied there. Rolling backups, the live
database, temporary/test databases, and unrelated files are never copied.
Local D: backups succeed independently of this optional copy. A successful
local file copy is logged separately from cloud sync: a OneDrive red cross,
sync error, or full cloud storage means the archive is **not** cloud-protected
until OneDrive itself confirms that it has synced. The app does not change
OneDrive settings or delete/move other OneDrive files.

To make backups run on a three-day schedule even when you do not open the app,
you may create a Task Scheduler task manually:

1. In **Task Scheduler**, choose **Create Task** and give it a clear name such
   as `Josh's Corner backup`.
2. Add a trigger that repeats every three days at a convenient time.
3. For **Program/script**, use
   `<project-root>\.venv\Scripts\python.exe`.
4. For **Add arguments**, use `scripts\backup_database.py`.
5. For **Start in**, use `<project-root>`.

No scheduled task is created by the project itself.

## Restore and migrations

Restore testing always targets a separate database:

```powershell
.\.venv\Scripts\python.exe scripts\restore_database.py backups\monthly\joshs_corner_YYYY-MM-DD_HHMMSS.db --target restore.test.db
```

Never overwrite `instance\joshs_corner.db` while the application is running.
Live replacement requires the explicit `--replace-live` option and creates a
fresh, validated safety backup first. Stop and confirm the exact backup before
performing that live replacement.

Use Flask-Migrate for every schema change. Before applying a future migration,
create and validate a backup, check migration status, run
`python scripts\migrate_safely.py`, then run the integrity and application
tests.
