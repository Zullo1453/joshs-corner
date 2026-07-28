from datetime import datetime, timezone

from app.extensions import db
from app.models import Todo


def add_todo(app, text, completed=False, completed_at=None):
    with app.app_context():
        todo = Todo(
            text=text,
            is_completed=completed,
            completed_at=completed_at,
        )
        db.session.add(todo)
        db.session.commit()
        return todo.id


def test_todos_page_loads_with_empty_states(client):
    response = client.get("/todos/")

    assert response.status_code == 200
    assert b"Add To-Do" in response.data
    assert b"Nothing left to do. Nicely done." in response.data
    assert b"Completed tasks will appear here." in response.data
    assert b"0 remaining" in response.data


def test_create_task_uses_expected_form_endpoint(client, app):
    page = client.get("/todos/")
    assert b'action="/todos/new"' in page.data
    assert b'method="post"' in page.data

    response = client.post("/todos/new", data={"text": "Buy groceries"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Buy groceries" in response.data
    assert b"1 remaining" in response.data

    with app.app_context():
        todo = Todo.query.one()
        assert todo.text == "Buy groceries"
        assert todo.is_completed is False
        assert todo.completed_at is None


def test_blank_or_whitespace_task_is_rejected(client, app):
    response = client.post("/todos/new", data={"text": "   "})

    assert response.status_code == 400
    assert b"Tasks need between 1 and 300 characters." in response.data
    with app.app_context():
        assert Todo.query.count() == 0


def test_task_length_is_validated(client, app):
    response = client.post("/todos/new", data={"text": "x" * 301})

    assert response.status_code == 400
    with app.app_context():
        assert Todo.query.count() == 0


def test_complete_task_moves_to_archive_and_stores_timestamp(client, app):
    todo_id = add_todo(app, "Finish report")

    response = client.post(f"/todos/{todo_id}/complete", follow_redirects=True)
    assert response.status_code == 200
    assert b"Finish report" in response.data
    assert b"Old To-Dos" in response.data
    assert b"1 remaining" not in response.data
    assert b"0 remaining" in response.data
    assert b'aria-expanded="true"' in response.data

    with app.app_context():
        todo = db.session.get(Todo, todo_id)
        assert todo.is_completed is True
        assert todo.completed_at is not None


def test_completion_date_uses_australian_day_month_year_format(client, app):
    completed_at = datetime(2026, 7, 28, 8, 42, tzinfo=timezone.utc)
    add_todo(app, "Archived task", completed=True, completed_at=completed_at)

    response = client.get("/todos/?archive=1")

    assert b"Completed 28 July 2026" in response.data


def test_completed_text_has_no_strikethrough_presentation(client, app):
    add_todo(app, "Readable completed task", completed=True, completed_at=datetime.now(timezone.utc))

    page = client.get("/todos/?archive=1")
    stylesheet = client.get("/static/css/todos.css")

    assert b"Readable completed task" in page.data
    assert b"text-decoration: line-through" not in stylesheet.data


def test_restore_clears_timestamp_and_recomplete_creates_new_timestamp(client, app):
    todo_id = add_todo(app, "Repeat task")

    client.post(f"/todos/{todo_id}/complete")
    with app.app_context():
        first_timestamp = db.session.get(Todo, todo_id).completed_at
        assert first_timestamp is not None

    client.post(f"/todos/{todo_id}/restore")
    with app.app_context():
        restored = db.session.get(Todo, todo_id)
        assert restored.is_completed is False
        assert restored.completed_at is None

    client.post(f"/todos/{todo_id}/complete")
    with app.app_context():
        re_completed = db.session.get(Todo, todo_id)
        assert re_completed.is_completed is True
        assert re_completed.completed_at is not None
        assert re_completed.completed_at != first_timestamp


def test_delete_active_task(client, app):
    todo_id = add_todo(app, "Delete active")

    response = client.post(f"/todos/{todo_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"Nothing left to do. Nicely done." in response.data
    with app.app_context():
        assert db.session.get(Todo, todo_id) is None


def test_delete_archived_task(client, app):
    todo_id = add_todo(app, "Delete archived", completed=True, completed_at=datetime.now(timezone.utc))

    response = client.post(f"/todos/{todo_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"Completed tasks will appear here." in response.data
    with app.app_context():
        assert db.session.get(Todo, todo_id) is None


def test_active_and_archived_counts(client, app):
    add_todo(app, "Active one")
    add_todo(app, "Active two")
    add_todo(app, "Archived", completed=True, completed_at=datetime.now(timezone.utc))

    response = client.get("/todos/")

    assert b"2 remaining" in response.data
    assert b'<span class="archive-count">1</span>' in response.data


def test_archive_collapse_control_and_delete_confirmation_assets(client, app):
    add_todo(app, "Archived", completed=True, completed_at=datetime.now(timezone.utc))

    page = client.get("/todos/")
    script = client.get("/static/js/todos.js")

    assert b'data-archive-toggle' in page.data
    assert b'aria-expanded="false"' in page.data
    assert b"archive.classList.toggle(\"open\")" in script.data
    assert b"Delete this to-do? This cannot be undone." in script.data


def test_missing_task_ids_return_not_found(client):
    for action in ("complete", "restore", "delete"):
        assert client.post(f"/todos/999999/{action}").status_code == 404
