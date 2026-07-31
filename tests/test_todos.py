from datetime import date, datetime, timezone
from pathlib import Path

from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models import Todo, TodoActivity


TODAY = date(2026, 7, 31)


def configure_today(app, value=TODAY):
    app.config["TODOS_TODAY"] = value


def add_todo(app, text, *, location="backlog", status="active", scheduled_date=None, completed_at=None):
    with app.app_context():
        todo = Todo(
            text=text, current_location=location, status=status,
            scheduled_date=scheduled_date, is_completed=status == "completed",
            completed_at=completed_at,
            archived_at=completed_at if location == "archived" else None,
        )
        db.session.add(todo)
        db.session.commit()
        return todo.id


def activities(app, todo_id):
    with app.app_context():
        return [item.event_type for item in db.session.execute(db.select(TodoActivity).where(TodoActivity.todo_id == todo_id)).scalars()]


def test_today_page_empty_state_and_three_views(client, app):
    configure_today(app)
    page = client.get("/todos/")
    assert page.status_code == 200
    assert b"Daily focus" in page.data and b"Nothing scheduled for today" in page.data
    assert client.get("/todos/backlog").status_code == 200
    assert client.get("/todos/history").status_code == 200


def test_create_today_task_and_reject_blank(client, app):
    configure_today(app)
    assert b'action="/todos/' in client.get("/todos/").data
    result = client.post("/todos/new", data={"text": "Buy groceries"}, follow_redirects=True)
    assert result.status_code == 200 and b"Buy groceries" in result.data
    with app.app_context():
        todo = db.session.execute(db.select(Todo)).scalar_one()
        assert (todo.current_location, todo.status, todo.scheduled_date, todo.original_date) == ("dated", "active", TODAY, TODAY)
    assert activities(app, todo.id) == ["created_today"]
    assert client.post("/todos/new", data={"text": "   "}).status_code == 400
    assert client.post("/todos/new", data={"text": "x" * 301}).status_code == 400


def test_backlog_create_move_and_schedule(client, app):
    configure_today(app)
    response = client.post("/todos/backlog/new", data={"text": "Plan holiday"}, follow_redirects=True)
    assert b"Plan holiday" in response.data
    with app.app_context():
        todo = db.session.execute(db.select(Todo)).scalar_one()
        assert todo.current_location == "backlog" and todo.scheduled_date is None
    client.post(f"/todos/{todo.id}/move-today")
    with app.app_context():
        assert db.session.get(Todo, todo.id).scheduled_date == TODAY
    client.post(f"/todos/{todo.id}/move-backlog")
    client.post(f"/todos/{todo.id}/schedule", data={"scheduled_date": "2026-08-03", "return_to": "backlog"})
    with app.app_context():
        saved = db.session.get(Todo, todo.id)
        assert saved.current_location == "dated" and saved.scheduled_date == date(2026, 8, 3)
    assert activities(app, todo.id) == ["created_backlog", "moved_to_today", "moved_to_backlog", "scheduled"]


def test_carry_forward_is_idempotent_and_preserves_origin(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Yesterday task", location="dated", scheduled_date=date(2026, 7, 29))
    first = client.get("/todos/")
    second = client.get("/todos/")
    assert b"Yesterday task" in first.data and b"Carried over from 29 July 2026" in second.data
    with app.app_context():
        todo = db.session.get(Todo, todo_id)
        assert todo.scheduled_date == TODAY and todo.carried_from_date == date(2026, 7, 29) and todo.carry_count == 1
        assert db.session.execute(db.select(TodoActivity).where(TodoActivity.todo_id == todo_id, TodoActivity.event_type == "carried_forward")).scalars().all()
    assert activities(app, todo_id).count("carried_forward") == 1


def test_completed_and_archived_tasks_do_not_carry(client, app):
    configure_today(app)
    completed_id = add_todo(app, "Completed old", location="dated", status="completed", scheduled_date=date(2026, 7, 30), completed_at=datetime.now(timezone.utc))
    archived_id = add_todo(app, "Archived old", location="archived", status="archived", scheduled_date=date(2026, 7, 30))
    client.get("/todos/")
    with app.app_context():
        assert db.session.get(Todo, completed_id).scheduled_date == date(2026, 7, 30)
        assert db.session.get(Todo, archived_id).scheduled_date == date(2026, 7, 30)


def test_complete_reopen_and_hide_completed_today(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Finish report", location="dated", scheduled_date=TODAY)
    page = client.post(f"/todos/{todo_id}/complete", data={"return_to": "today"}, follow_redirects=True)
    assert b"Completed today" in page.data and b"Finish report" in page.data
    assert b"text-decoration:line-through" in client.get("/static/css/todos.css").data
    with app.app_context():
        first = db.session.get(Todo, todo_id).completed_at
        assert first and db.session.get(Todo, todo_id).status == "completed"
    hidden = client.get("/todos/?hide_completed=1")
    assert b"Finish report" not in hidden.data
    client.post(f"/todos/{todo_id}/reopen", data={"return_to": "today"})
    with app.app_context():
        assert db.session.get(Todo, todo_id).completed_at is None
    client.post(f"/todos/{todo_id}/complete", data={"return_to": "today"})
    with app.app_context():
        assert db.session.get(Todo, todo_id).completed_at != first


def test_edit_archive_and_history_are_auditable(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Draft task", location="dated", scheduled_date=TODAY)
    client.post(f"/todos/{todo_id}/edit", data={"text": "Edited task", "return_to": "today"})
    client.post(f"/todos/{todo_id}/delete", data={"return_to": "today"})
    with app.app_context():
        todo = db.session.get(Todo, todo_id)
        assert todo is not None and todo.status == "archived" and todo.archived_at is not None
    history = client.get("/todos/history?date=2026-07-31")
    assert b"Edited task" in history.data and b"Archived" in history.data
    assert activities(app, todo_id) == ["edited", "archived"]


def test_history_accepts_selected_date_and_bad_dates_fail(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Scheduled", location="backlog")
    client.post(f"/todos/{todo_id}/schedule", data={"scheduled_date": "2026-08-02", "return_to": "backlog"})
    page = client.get("/todos/history?date=2026-08-02")
    assert b"Scheduled" in page.data and b"Scheduled" in page.data
    assert client.get("/todos/history?date=not-a-date").status_code == 400
    assert client.post(f"/todos/{todo_id}/schedule", data={"scheduled_date": "2026-07-30"}).status_code == 400


def test_invalid_task_actions_and_ids_are_safe(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Backlog", location="backlog")
    assert client.post(f"/todos/{todo_id}/move-backlog").status_code == 400
    assert client.post(f"/todos/{todo_id}/complete").status_code == 302
    assert client.post(f"/todos/{todo_id}/complete").status_code == 400
    for action in ("complete", "restore", "delete", "schedule", "edit"):
        assert client.post(f"/todos/999999/{action}").status_code == 404


def test_archive_confirmation_and_post_only_controls(client, app):
    configure_today(app)
    add_todo(app, "Archive me", location="dated", scheduled_date=TODAY)
    page = client.get("/todos/")
    script = client.get("/static/js/todos.js")
    assert b'data-archive-form' in page.data
    assert b"Archive this task? Its history will be retained." in script.data
    assert client.get("/todos/new").status_code == 405


def test_daily_todo_migration_maps_legacy_rows_without_guessing_dates(tmp_path):
    database = tmp_path / "todo-migration.db"
    migration_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with migration_app.app_context():
        upgrade(directory=str(migrations), revision="d51f6c8e9a32")
        db.session.execute(text("INSERT INTO todo (text, is_completed, completed_at, created_at, updated_at) VALUES ('Legacy active', 0, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        db.session.execute(text("INSERT INTO todo (text, is_completed, completed_at, created_at, updated_at) VALUES ('Legacy completed', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        db.session.commit()
        upgrade(directory=str(migrations), revision="head")
        rows = db.session.execute(text("SELECT text, current_location, status, scheduled_date FROM todo ORDER BY id")).all()
        assert rows == [("Legacy active", "backlog", "active", None), ("Legacy completed", "archived", "completed", None)]
        assert db.session.execute(text("SELECT count(*) FROM todo_activity")).scalar_one() == 2
        assert "scheduled_date" in {column["name"] for column in inspect(db.engine).get_columns("todo")}
        downgrade(directory=str(migrations), revision="d51f6c8e9a32")
        assert "scheduled_date" not in {column["name"] for column in inspect(db.engine).get_columns("todo")}
