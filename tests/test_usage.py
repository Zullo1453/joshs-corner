from datetime import date
from pathlib import Path

from app.extensions import db
from app.models import Deadline, Exercise, ExerciseSet, GameJournal, JournalEntry, Note, Project, ReadingItem, Run, RunRoute, Todo, UpcomingEvent, WatchlistItem, WorkoutExercise, WorkoutSession, WorkoutTemplate
from app.usage import UsageService, format_bytes


def test_size_formatting_uses_friendly_storage_units():
    assert format_bytes(0) == "0 KB"
    assert format_bytes(1024) == "1 KB"
    assert format_bytes(1536) == "1.5 KB"
    assert format_bytes(2 * 1024 * 1024) == "2 MB"
    assert format_bytes(3 * 1024 * 1024 * 1024) == "3 GB"


def test_local_usage_counts_only_known_data_directories(app, tmp_path):
    database, uploads, backups = tmp_path / "corner.db", tmp_path / "uploads", tmp_path / "backups"
    database.write_bytes(b"d" * 2048)
    (uploads / "nested").mkdir(parents=True)
    (uploads / "nested" / "photo.webp").write_bytes(b"u" * 300)
    (backups / "rolling").mkdir(parents=True)
    (backups / "monthly").mkdir()
    (backups / "rolling" / "joshs_corner_backup_a.zip").write_bytes(b"r" * 400)
    (backups / "monthly" / "joshs_corner_backup_b.zip").write_bytes(b"m" * 500)
    (backups / "joshs_corner_legacy-root.db").write_bytes(b"l" * 100)
    (backups / "rolling" / "joshs_corner_legacy-rolling.db").write_bytes(b"l" * 200)
    (backups / "monthly" / "joshs_corner_legacy-monthly.db").write_bytes(b"l" * 300)
    (backups / "migration-safety").mkdir()
    (backups / "migration-safety" / "joshs_corner_backup_historical.zip").write_bytes(b"h" * 700)
    (backups / "unrelated.bin").write_bytes(b"x" * 9999)
    with app.app_context():
        usage = UsageService(app, database_path=database, upload_directory=uploads, backup_root=backups).local_usage()
    assert usage["database"]["bytes"] == 2048
    assert usage["uploads"] == {"bytes": 300, "count": 1, "label": "0.3 KB"}
    assert usage["backups"]["bytes"] == 1500 and usage["backups"]["package_count"] == 2
    assert usage["backups"]["rolling"] == {"count": 1, "limit": 10}
    assert usage["backups"]["monthly"] == {"count": 1, "limit": 12}
    assert usage["backups"]["legacy"] == {"count": 3}
    assert usage["total"]["bytes"] == 3848


def test_usage_handles_absent_optional_directories_without_creating_them(app, tmp_path):
    missing = tmp_path / "does-not-exist"
    with app.app_context():
        usage = UsageService(app, database_path=tmp_path / "missing.db", upload_directory=missing, backup_root=missing).local_usage()
    assert usage["uploads"]["bytes"] == 0 and usage["backups"]["bytes"] == 0
    assert not missing.exists()


def test_usage_record_counts_and_page_are_read_only_and_private(app, client, tmp_path, monkeypatch):
    with app.app_context():
        session = WorkoutSession(workout_date=date(2026, 9, 4))
        exercise = Exercise(name="Fictional Push-up", body_part="Chest", tracking_type="bodyweight")
        occurrence = WorkoutExercise(session=session, exercise=exercise)
        occurrence.sets.append(ExerciseSet(set_number=1, reps=10))
        route = RunRoute(name="Fictional Route", name_key="fictional route")
        db.session.add_all([JournalEntry(entry_date=date(2026, 9, 4)), Note(title="Fictional note"), Todo(text="Fictional task"), Project(title="Fictional project"), Deadline(title="Fictional deadline", due_date=date(2026, 9, 5)), UpcomingEvent(title="Fictional event", event_date=date(2026, 9, 6)), GameJournal(title="Fictional game"), WatchlistItem(title="Fictional film", media_type="Film"), ReadingItem(title="Fictional book"), WorkoutTemplate(name="Fictional template"), session, route])
        db.session.add(Run(route=route, run_date=date(2026, 9, 4), distance_km=5, elapsed_seconds=1800))
        db.session.commit()
        before = db.session.scalar(db.select(db.func.count(Todo.id)))
        counts = {item["label"]: item["count"] for item in UsageService(app).database_counts()}
        assert counts["Journal entries"] == counts["Exercise sets"] == counts["Runs"] == 1
    monkeypatch.setattr("socket.create_connection", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Usage must not make network calls")))
    response = client.get("/automations/usage")
    assert response.status_code == 200
    assert b"Supabase" in response.data and b"Vercel" in response.data and response.data.count(b"Not connected") == 2
    assert b"Current backup packages" in response.data and b"Legacy database backups" in response.data
    assert b"Fictional task" not in response.data and str(Path(app.instance_path)).encode() not in response.data and b"D:\\" not in response.data
    assert client.post("/automations/usage").status_code == 405
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Todo.id))) == before
