"""Stage 2A PostgreSQL contracts use no network or real user data."""
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Date, DateTime, Numeric, Time, create_mock_engine
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app import create_app
from app.extensions import db
from app.models import Deadline, Exercise, ExerciseSet, RecurrenceRule, Run, TaskOccurrence
from app.recurrence import generate_occurrences
from app.runtime import database_engine_options, normalize_database_uri
from app.search import PostgresSearchAdapter, SOURCES, UniversalSearchService


def test_common_postgres_urls_select_psycopg_3_and_keep_explicit_drivers():
    assert normalize_database_uri("postgres://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert normalize_database_uri("postgresql://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    explicit = "postgresql+psycopg://user:pass@host/db"
    assert normalize_database_uri(explicit) == explicit
    assert normalize_database_uri(" sqlite:///:memory: ") == "sqlite:///:memory:"


def test_engine_options_are_dialect_separated_and_postgres_is_serverless_safe(monkeypatch):
    assert database_engine_options("sqlite:///:memory:") == {}
    assert database_engine_options("postgresql+psycopg://user:secret@host/db") == {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 1,
        "max_overflow": 0,
        "connect_args": {"prepare_threshold": None},
    }
    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@host/db")
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.app_context():
        assert db.engine.url.drivername == "postgresql+psycopg"
        assert db.engine.pool._pre_ping is True
        assert db.engine.pool._recycle == 300
        assert db.engine.pool.size() == 1
        assert db.engine.pool._max_overflow == 0
        assert app.config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]["prepare_threshold"] is None


def test_explicit_sqlite_test_config_never_inherits_postgres_engine_options(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@host/db")
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
    })
    assert app.config["SQLALCHEMY_ENGINE_OPTIONS"] == {}
    with app.app_context():
        assert db.engine.dialect.name == "sqlite"


def test_flask_secret_key_has_an_environment_boundary(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "synthetic-test-secret")
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    assert app.secret_key == "synthetic-test-secret"


def test_postgres_search_statements_compile_for_every_source_and_keep_scope_hook():
    dialect = postgresql.dialect()

    class Scoped(UniversalSearchService):
        def __init__(self):
            self.seen = []

        def scope_statement(self, statement, source):
            self.seen.append(source.kind)
            return statement

    service = Scoped()
    adapter = PostgresSearchAdapter()
    compiled = {}
    for source in SOURCES:
        statement = adapter.statement(service, source, "public economics", ("public", "economics"))
        compiled[source.kind] = str(statement.compile(dialect=dialect))
    assert service.seen == [source.kind for source in SOURCES]
    assert all("strpos" in sql and "regexp_replace" in sql and "LIMIT" in sql for sql in compiled.values())
    assert "row_number() OVER" in compiled["Play log"]
    assert "to_char" in compiled["Journal"]
    assert "jc_search_text" not in "".join(compiled.values())


def test_models_compile_as_postgres_with_native_types_and_boolean_defaults():
    statements = []
    engine = create_mock_engine(
        "postgresql+psycopg://",
        lambda sql, *multiparams, **params: statements.append(str(sql.compile(dialect=postgresql.dialect()))),
    )
    db.metadata.create_all(engine)
    ddl = "\n".join(statements)
    assert "NUMERIC(8, 2)" in ddl and "NUMERIC(8, 3)" in ddl
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert " DATE" in ddl and " TIME WITHOUT TIME ZONE" in ddl
    assert "DEFAULT true" in ddl and "DEFAULT false" in ddl
    assert "BOOLEAN DEFAULT '1'" not in ddl and "BOOLEAN DEFAULT '0'" not in ddl


def test_boolean_and_numeric_defaults_compile_for_both_dialects():
    postgres_exercise = str(CreateTable(Exercise.__table__).compile(dialect=postgresql.dialect()))
    sqlite_exercise = str(CreateTable(Exercise.__table__).compile(dialect=sqlite.dialect()))
    assert "DEFAULT false" in postgres_exercise and "DEFAULT true" in postgres_exercise
    assert "DEFAULT 0" in sqlite_exercise and "DEFAULT 1" in sqlite_exercise
    assert isinstance(ExerciseSet.__table__.c.weight_kg.type, Numeric)
    assert ExerciseSet.__table__.c.weight_kg.type.scale == 2
    assert Run.__table__.c.distance_km.type.scale == 3
    assert isinstance(Deadline.__table__.c.due_date.type, Date)
    assert isinstance(Run.__table__.c.run_time.type, Time)
    assert isinstance(TaskOccurrence.__table__.c.completed_at.type, DateTime)
    assert TaskOccurrence.__table__.c.completed_at.type.timezone is True


def test_sqlite_round_trips_booleans_decimals_dates_times_and_timestamps(app):
    with app.app_context():
        exercise = Exercise(name="Synthetic", body_part="Other")
        db.session.add(exercise)
        db.session.flush()
        from app.models import RunRoute, WorkoutExercise, WorkoutSession
        route = RunRoute(name="Synthetic route", name_key="synthetic route", distance_km=Decimal("6.420"))
        session = WorkoutSession(workout_date=date(2026, 9, 11), started_at=datetime(2026, 9, 11, tzinfo=timezone.utc))
        occurrence = WorkoutExercise(session=session, exercise=exercise)
        saved_set = ExerciseSet(workout_exercise=occurrence, set_number=1, weight_kg=Decimal("22.50"), reps=5)
        run = Run(route=route, run_date=date(2026, 9, 11), run_time=time(6, 30), distance_km=Decimal("2.500"), elapsed_seconds=900)
        db.session.add_all([route, session, saved_set, run])
        db.session.commit()
        assert exercise.active is True and exercise.is_favorite is False
        assert saved_set.weight_kg == Decimal("22.50")
        assert run.distance_km == Decimal("2.500") and route.distance_km == Decimal("6.420")
        assert run.run_date == date(2026, 9, 11) and run.run_time == time(6, 30)


def test_generation_conflict_uses_savepoint_and_preserves_later_dates(app, monkeypatch):
    with app.app_context():
        rule = RecurrenceRule(
            text="Synthetic daily", recurrence_type="daily", interval=1,
            start_date=date(2026, 9, 10),
        )
        db.session.add(rule)
        db.session.commit()
        session = db.session()
        original_flush = session.flush
        raised = False

        def conflict_once(*args, **kwargs):
            nonlocal raised
            if not raised and any(isinstance(item, TaskOccurrence) for item in session.new):
                raised = True
                raise IntegrityError("synthetic insert", {}, Exception("synthetic conflict"))
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", conflict_once)
        generate_occurrences(date(2026, 9, 11))
        saved = db.session.scalars(
            db.select(TaskOccurrence).order_by(TaskOccurrence.due_date)
        ).all()
        assert raised is True
        assert [item.due_date for item in saved] == [date(2026, 9, 11)]

def test_historical_migrations_have_postgres_safe_boolean_defaults():
    root = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for unsafe in (
        "sa.Boolean(), server_default='1'", "sa.Boolean(), server_default='0'",
        'sa.Boolean(), server_default="1"', 'sa.Boolean(), server_default="0"',
    ):
        assert unsafe not in sources