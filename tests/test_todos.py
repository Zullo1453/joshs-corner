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


def add_todo(app, text, *, location="backlog", status="active", scheduled_date=None, completed_at=None, rollover_enabled=True, project_id=None):
    with app.app_context():
        todo = Todo(
            text=text, current_location=location, status=status,
            scheduled_date=scheduled_date, is_completed=status == "completed",
            completed_at=completed_at,
            archived_at=completed_at if location == "archived" else None,
            rollover_enabled=rollover_enabled, project_id=project_id,
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
        assert (todo.current_location, todo.status, todo.scheduled_date, todo.original_date, todo.rollover_enabled) == ("dated", "active", TODAY, TODAY, False)
    assert activities(app, todo.id) == ["created_today"]
    assert client.post("/todos/new", data={"text": "   "}).status_code == 400
    assert client.post("/todos/new", data={"text": "x" * 301}).status_code == 400


def test_today_creation_opt_in_and_rollover_toggle_are_auditable(client, app):
    configure_today(app)
    page = client.get("/todos/")
    assert b"Carry forward if incomplete" in page.data and b"rollover_enabled" in page.data
    client.post("/todos/new", data={"text": "Carry me", "rollover_enabled": "true"})
    with app.app_context():
        todo = db.session.execute(db.select(Todo)).scalar_one()
        assert todo.rollover_enabled is True
    changed = client.post(f"/todos/{todo.id}/rollover", data={"rollover_enabled": "false", "return_to": "today"}, follow_redirects=True)
    assert changed.status_code == 200 and b"Enable rollover" in changed.data
    with app.app_context():
        todo = db.session.get(Todo, todo.id)
        event = db.session.execute(db.select(TodoActivity).where(TodoActivity.todo_id == todo.id)).scalars().all()[-1]
        assert todo.rollover_enabled is False
        assert event.event_type == "rollover_changed"
        assert event.metadata_json == '{"previous_value": true, "new_value": false}'
    client.post(f"/todos/{todo.id}/rollover", data={"rollover_enabled": "false", "return_to": "today"})
    assert activities(app, todo.id).count("rollover_changed") == 1


def test_disabled_rollover_leaves_overdue_task_in_history_without_repeated_events(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Keep on Tuesday", location="dated", scheduled_date=date(2026, 7, 29), rollover_enabled=False)
    client.get("/todos/")
    client.get("/todos/")
    with app.app_context():
        todo = db.session.get(Todo, todo_id)
        assert (todo.scheduled_date, todo.carry_count) == (date(2026, 7, 29), 0)
        assert not db.session.execute(db.select(TodoActivity).where(TodoActivity.todo_id == todo_id)).scalars().all()
    history = client.get("/todos/history?date=2026-07-29")
    assert b"Keep on Tuesday" in history.data and b"Incomplete" in history.data and b"rollover disabled" in history.data


def test_rollover_preserves_task_identity_and_unrelated_lifecycle_fields(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Same task", location="dated", scheduled_date=date(2026, 7, 30), rollover_enabled=True)
    with app.app_context():
        todo = db.session.get(Todo, todo_id)
        todo.original_date = date(2026, 7, 30)
        db.session.commit()
    client.get("/todos/")
    with app.app_context():
        todo = db.session.get(Todo, todo_id)
        assert (todo.id, todo.scheduled_date, todo.original_date, todo.carry_count, todo.rollover_enabled) == (todo_id, TODAY, date(2026, 7, 30), 1, True)


def test_rollover_route_rejects_bad_values_and_inactive_or_missing_tasks(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Active", location="dated", scheduled_date=TODAY)
    assert client.post(f"/todos/{todo_id}/rollover", data={"rollover_enabled": "maybe"}).status_code == 400
    assert client.post("/todos/999999/rollover", data={"rollover_enabled": "true"}).status_code == 404
    client.post(f"/todos/{todo_id}/complete", data={"return_to": "today"})
    assert client.post(f"/todos/{todo_id}/rollover", data={"rollover_enabled": "false"}).status_code == 400


def test_backlog_create_move_and_schedule(client, app):
    configure_today(app)
    response = client.post("/todos/backlog/new", data={"text": "Plan holiday"}, follow_redirects=True)
    assert b"Plan holiday" in response.data
    with app.app_context():
        todo = db.session.execute(db.select(Todo)).scalar_one()
        assert todo.current_location == "backlog" and todo.scheduled_date is None and todo.rollover_enabled is True
    client.post(f"/todos/{todo.id}/move-today")
    with app.app_context():
        moved = db.session.get(Todo, todo.id)
        assert moved.scheduled_date == TODAY and moved.rollover_enabled is True
    client.post(f"/todos/{todo.id}/move-backlog")
    client.post(f"/todos/{todo.id}/schedule-backlog", data={"scheduled_date": "2026-08-03"})
    with app.app_context():
        saved = db.session.get(Todo, todo.id)
        assert saved.current_location == "dated" and saved.scheduled_date == date(2026, 8, 3)
    assert activities(app, todo.id) == ["created_backlog", "moved_to_today", "moved_to_backlog", "backlog_scheduled"]


def test_backlog_schedule_action_moves_the_same_task_to_today(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Schedule for today", rollover_enabled=True)
    page = client.get("/todos/backlog")
    script = client.get("/static/js/todos.js")
    card = page.data.split(f'data-todo-id="{todo_id}"'.encode(), 1)[1].split(b"</article>", 1)[0]
    assert b"data-task-schedule" in card and b"data-task-schedule-form" in card
    assert b"Schedule" in card and b"Cancel" in card
    assert b"data-task-schedule-cancel" in script.data and b"data-task-schedule-form" in script.data

    response = client.post(f"/todos/{todo_id}/schedule-backlog", data={"scheduled_date": TODAY.isoformat()}, follow_redirects=True)
    assert response.status_code == 200 and b"Schedule for today" in response.data
    with app.app_context():
        todo = db.session.get(Todo, todo_id)
        assert (todo.id, todo.current_location, todo.scheduled_date, todo.project_id, todo.rollover_enabled) == (todo_id, "dated", TODAY, None, True)
        assert db.session.execute(db.select(Todo)).scalars().all().__len__() == 1
        event = db.session.execute(db.select(TodoActivity).where(TodoActivity.todo_id == todo_id)).scalar_one()
        assert event.event_type == "backlog_moved_to_today" and event.metadata_json == '{"source": "backlog"}'
    assert b"Schedule for today" not in client.get("/todos/backlog").data
    history = client.get(f"/todos/history?date={TODAY.isoformat()}")
    assert b"Moved from Backlog to Today" in history.data


def test_backlog_future_schedule_reschedule_and_return_preserve_identity(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Future standalone", rollover_enabled=False)
    future = date(2026, 8, 3)
    later = date(2026, 8, 5)
    client.post(f"/todos/{todo_id}/schedule-backlog", data={"scheduled_date": future.isoformat()})
    with app.app_context():
        todo = db.session.get(Todo, todo_id)
        assert (todo.id, todo.current_location, todo.scheduled_date, todo.rollover_enabled, todo.project_id) == (todo_id, "dated", future, False, None)
    assert b"Future standalone" not in client.get("/todos/").data
    backlog = client.get("/todos/backlog")
    assert b"Upcoming" in backlog.data and b"Future standalone" in backlog.data
    client.post(f"/todos/{todo_id}/schedule", data={"scheduled_date": later.isoformat(), "return_to": "backlog"})
    client.post(f"/todos/{todo_id}/move-backlog")
    with app.app_context():
        todo = db.session.get(Todo, todo_id)
        assert (todo.id, todo.current_location, todo.scheduled_date, todo.rollover_enabled, todo.project_id) == (todo_id, "backlog", None, False, None)
        assert db.session.execute(db.select(Todo)).scalars().all().__len__() == 1
    assert activities(app, todo_id) == ["backlog_scheduled", "rescheduled", "moved_to_backlog"]
    history = client.get(f"/todos/history?date={later.isoformat()}")
    assert b"Returned to Backlog" in history.data and b"Rescheduled" in history.data


def test_backlog_schedule_validates_dates_and_rejects_project_or_archived_tasks(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Standalone")
    assert client.post(f"/todos/{todo_id}/schedule-backlog", data={"scheduled_date": "2026-07-30"}).status_code == 400
    assert client.post(f"/todos/{todo_id}/schedule-backlog", data={"scheduled_date": "not-a-date"}).status_code == 400
    assert client.post(f"/todos/{todo_id}/schedule", data={"scheduled_date": TODAY.isoformat()}).status_code == 400
    assert client.post("/todos/999999/schedule-backlog", data={"scheduled_date": TODAY.isoformat()}).status_code == 404
    project_todo = add_todo(app, "Project task", project_id=1)
    assert client.post(f"/todos/{project_todo}/schedule-backlog", data={"scheduled_date": TODAY.isoformat()}).status_code == 400
    scheduled_project = add_todo(app, "Scheduled project task", location="dated", scheduled_date=TODAY, project_id=1)
    assert client.post(f"/todos/{scheduled_project}/move-backlog").status_code == 400
    client.post(f"/todos/{todo_id}/delete", data={"return_to": "backlog"})
    assert client.post(f"/todos/{todo_id}/schedule-backlog", data={"scheduled_date": TODAY.isoformat()}).status_code == 400


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


def test_editing_active_tasks_preserves_lifecycle_fields_and_avoids_noop_events(client, app):
    configure_today(app)
    todo_id = add_todo(app, "  Original task  ", location="dated", scheduled_date=TODAY)
    with app.app_context():
        todo = db.session.get(Todo, todo_id)
        todo.text = "Original task"
        todo.original_date = date(2026, 7, 29)
        todo.carried_from_date = date(2026, 7, 30)
        todo.carry_count = 2
        db.session.commit()

    updated = client.post(f"/todos/{todo_id}/edit", data={"text": "  Updated task  ", "return_to": "today"}, follow_redirects=True)
    assert updated.status_code == 200 and b"Updated task" in updated.data
    with app.app_context():
        todo = db.session.get(Todo, todo_id)
        event = db.session.execute(db.select(TodoActivity).where(TodoActivity.todo_id == todo_id)).scalar_one()
        assert (todo.text, todo.current_location, todo.scheduled_date, todo.original_date, todo.carried_from_date, todo.carry_count, todo.rollover_enabled, todo.status, todo.is_completed, todo.completed_at, todo.archived_at) == (
            "Updated task", "dated", TODAY, date(2026, 7, 29), date(2026, 7, 30), 2, True, "active", False, None, None
        )
        assert event.event_type == "edited" and event.metadata_json == '{"previous_title": "Original task", "new_title": "Updated task"}'
    assert client.post(f"/todos/{todo_id}/edit", data={"text": "Updated task", "return_to": "today"}).status_code == 302
    assert activities(app, todo_id) == ["edited"]
    assert client.post(f"/todos/{todo_id}/edit", data={"text": "   ", "return_to": "today"}).status_code == 400
    with app.app_context():
        assert db.session.execute(db.select(Todo).where(Todo.id == todo_id)).scalar_one().text == "Updated task"
        assert db.session.execute(db.select(Todo)).scalars().all().__len__() == 1


def test_editing_backlog_and_scheduled_tasks_updates_the_same_record(client, app):
    configure_today(app)
    backlog_id = add_todo(app, "Backlog original")
    client.post(f"/todos/{backlog_id}/edit", data={"text": "Backlog updated", "return_to": "backlog"})
    assert b"Backlog updated" in client.get("/todos/backlog").data
    client.post(f"/todos/{backlog_id}/schedule-backlog", data={"scheduled_date": "2026-08-03"})
    client.post(f"/todos/{backlog_id}/edit", data={"text": "Scheduled updated", "return_to": "backlog"})
    with app.app_context():
        todo = db.session.get(Todo, backlog_id)
        assert (todo.text, todo.current_location, todo.scheduled_date) == ("Scheduled updated", "dated", date(2026, 8, 3))
        assert db.session.execute(db.select(Todo)).scalars().all().__len__() == 1


def test_rescheduling_preserves_an_existing_rollover_preference(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Do not carry", location="dated", scheduled_date=date(2026, 8, 3), rollover_enabled=False)
    client.post(f"/todos/{todo_id}/schedule", data={"scheduled_date": "2026-08-04", "return_to": "backlog"})
    with app.app_context():
        assert db.session.get(Todo, todo_id).rollover_enabled is False


def test_task_edit_controls_are_inline_and_cancellation_does_not_submit_a_request(client, app):
    configure_today(app)
    active_id = add_todo(app, "Editable", location="dated", scheduled_date=TODAY)
    completed_id = add_todo(app, "Finished", location="dated", status="completed", scheduled_date=TODAY, completed_at=datetime.now(timezone.utc))
    page = client.get("/todos/")
    script = client.get("/static/js/todos.js")
    active_card = page.data.split(f'data-todo-id="{active_id}"'.encode(), 1)[1].split(b"</article>", 1)[0]
    completed_card = page.data.split(f'data-todo-id="{completed_id}"'.encode(), 1)[1].split(b"</article>", 1)[0]
    assert b"data-task-edit" in active_card and b"data-task-edit-form" in active_card
    assert b"data-task-edit" not in completed_card
    assert b"form.reset(); form.hidden = true" in script.data and b'event.key === "Escape"' in script.data
    assert b'event.key === "Enter"' in script.data and b"form.requestSubmit()" in script.data


def test_history_accepts_selected_date_and_bad_dates_fail(client, app):
    configure_today(app)
    todo_id = add_todo(app, "Scheduled", location="backlog")
    client.post(f"/todos/{todo_id}/schedule-backlog", data={"scheduled_date": "2026-08-02"})
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
    for action in ("complete", "restore", "delete", "schedule", "schedule-backlog", "edit"):
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
        rows = db.session.execute(text("SELECT text, current_location, status, scheduled_date, rollover_enabled FROM todo ORDER BY id")).all()
        assert rows == [("Legacy active", "backlog", "active", None, 1), ("Legacy completed", "archived", "completed", None, 1)]
        assert db.session.execute(text("SELECT count(*) FROM todo_activity")).scalar_one() == 2
        assert {"scheduled_date", "rollover_enabled"} <= {column["name"] for column in inspect(db.engine).get_columns("todo")}
        downgrade(directory=str(migrations), revision="d51f6c8e9a32")
        assert "scheduled_date" not in {column["name"] for column in inspect(db.engine).get_columns("todo")}
