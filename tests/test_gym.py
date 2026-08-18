from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from flask_migrate import downgrade, upgrade
from app.extensions import db
from app.gym import exercise_volume, heaviest_occurrence, max_weight, previous_occurrence, progress_points
from app.models import Exercise, ExerciseSet, WorkoutExercise, WorkoutSession


def add_occurrence(exercise, day, sets, hour=9):
    session = WorkoutSession(
        workout_date=day,
        started_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=hour),
    )
    occurrence = WorkoutExercise(session=session, exercise=exercise)
    for number, (weight, reps) in enumerate(sets, 1):
        occurrence.sets.append(ExerciseSet(set_number=number, weight_kg=Decimal(str(weight)), reps=reps))
    db.session.add(session)
    db.session.commit()
    return occurrence


def test_gym_empty_views_and_navigation(client):
    for path in ("/gym", "/gym/today", "/gym/exercises", "/gym/history"):
        response = client.get(path)
        assert response.status_code == 200
    response = client.get("/gym")
    assert b"Gym" in response.data
    assert b"Start today" in response.data


def test_exercise_lifecycle_and_today_set_persistence(app, client):
    response = client.post("/gym/exercises", data={"name": "Shoulder Press", "body_part": "Shoulders"})
    assert response.status_code == 302
    with app.app_context():
        exercise = db.session.scalar(db.select(Exercise))
        exercise_id = exercise.id
    client.post("/gym/today/start")
    client.post("/gym/today/exercises", data={"exercise_id": exercise_id})
    with app.app_context():
        occurrence = db.session.scalar(db.select(WorkoutExercise))
        occurrence_id = occurrence.id
    client.post(f"/gym/today/workout-exercises/{occurrence_id}/sets", data={"weight_kg": "22.5", "reps": "8"})
    with app.app_context():
        saved = db.session.scalar(db.select(ExerciseSet))
        assert saved.weight_kg == Decimal("22.50")
        set_id = saved.id
    client.post(f"/gym/sets/{set_id}/edit", data={"weight_kg": "22.5", "reps": "9"})
    assert b"22.5 kg" in client.get("/gym").data
    client.post(f"/gym/sets/{set_id}/remove")
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(ExerciseSet.id))) == 0
    client.post(f"/gym/exercises/{exercise_id}/archive")
    assert b"Archived" in client.get("/gym/exercises").data
    client.post(f"/gym/exercises/{exercise_id}/restore")
    with app.app_context():
        assert db.session.get(Exercise, exercise_id).active is True


def test_calculations_previous_heaviest_and_graph_points(app):
    with app.app_context():
        exercise = Exercise(name="Bench Press", body_part="Chest")
        unrelated = Exercise(name="Curl", body_part="Biceps")
        db.session.add_all((exercise, unrelated))
        db.session.commit()
        older = add_occurrence(exercise, date(2025, 12, 31), [(25, 4), (20, 8)])
        tied_more_reps = add_occurrence(exercise, date(2026, 1, 7), [(25, 6)], hour=10)
        most_recent_tie = add_occurrence(exercise, date(2026, 2, 3), [(25, 6)], hour=11)
        current = add_occurrence(exercise, date(2026, 2, 10), [(22.5, 6), (22.5, 5), (20, 8)])
        add_occurrence(unrelated, date(2026, 2, 11), [(99, 1)])
        assert exercise_volume(current) == Decimal("407.5")
        assert max_weight(current) == Decimal("22.5")
        assert previous_occurrence(exercise.id, current.workout_session_id).id == most_recent_tie.id
        assert heaviest_occurrence(exercise.id).id == most_recent_tie.id
        points = progress_points(exercise.id)
        assert [point["date"] for point in points] == ["2025-12-31", "2026-01-07", "2026-02-03", "2026-02-10"]
        assert points[-1]["max_weight"] == 22.5
        assert points[-1]["volume"] == 407.5
        assert points[-1]["sets"] == ["22.5 × 6", "22.5 × 5", "20 × 8"]
        assert older.id != heaviest_occurrence(exercise.id).id


def test_copy_previous_creates_independent_sets(app, client):
    with app.app_context():
        exercise = Exercise(name="Lateral Raise", body_part="Shoulders")
        db.session.add(exercise)
        db.session.commit()
        add_occurrence(exercise, date.today() - timedelta(days=3), [(7.5, 12), (7.5, 10)])
        exercise_id = exercise.id
    client.post("/gym/today/start")
    client.post("/gym/today/exercises", data={"exercise_id": exercise_id})
    with app.app_context():
        occurrence = db.session.scalar(db.select(WorkoutExercise).order_by(WorkoutExercise.id.desc()))
        occurrence_id = occurrence.id
    client.post(f"/gym/today/workout-exercises/{occurrence_id}/copy-previous")
    client.post(f"/gym/today/workout-exercises/{occurrence_id}/copy-previous")
    with app.app_context():
        copied = db.session.get(WorkoutExercise, occurrence_id)
        assert [(item.weight_kg, item.reps) for item in copied.sets] == [(Decimal("7.50"), 12), (Decimal("7.50"), 10)]
        assert len(copied.sets) == 2


def test_progress_and_history_pages_include_saved_workouts(app, client):
    with app.app_context():
        exercise = Exercise(name="Pull-up", body_part="Back")
        db.session.add(exercise)
        db.session.commit()
        add_occurrence(exercise, date.today() - timedelta(days=1), [(0, 8), (0, 7)])
        exercise_id = exercise.id
    assert b"Weight Progression" in client.get(f"/gym/exercises/{exercise_id}").data
    assert b"Session Volume" in client.get(f"/gym/exercises/{exercise_id}").data
    history = client.get("/gym/history")
    assert history.status_code == 200
    assert b"Pull-up" in history.data


def test_gym_migration_upgrades_downgrades_and_reupgrades(tmp_path):
    from app import create_app

    database = tmp_path / "gym-migration.db"
    migration_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with migration_app.app_context():
        upgrade(directory=str(migrations), revision="bb5f9a2c3d40")
        upgrade(directory=str(migrations), revision="head")
        tables = set(db.inspect(db.engine).get_table_names())
        assert {"exercise", "workout_session", "workout_exercise", "exercise_set"} <= tables
        downgrade(directory=str(migrations), revision="bb5f9a2c3d40")
        assert "exercise" not in db.inspect(db.engine).get_table_names()
        upgrade(directory=str(migrations), revision="head")
        assert "exercise_set" in db.inspect(db.engine).get_table_names()


def test_gym_posts_have_csrf_protection():
    from app import create_app

    secure = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "WTF_CSRF_ENABLED": True})
    with secure.app_context():
        db.create_all()
    client = secure.test_client()
    assert client.post("/gym/today/start").status_code == 400
    assert client.post("/gym/exercises", data={"name": "Blocked", "body_part": "Chest"}).status_code == 400
    with secure.app_context():
        db.drop_all()
