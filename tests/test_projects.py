from datetime import date
from pathlib import Path

from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models import Project, ProjectActivity, Todo


TODAY = date(2026, 7, 31)


def set_today(app, value=TODAY):
    app.config["TODOS_TODAY"] = value


def create_project(client, title="Make a video", description="Four steps"):
    response = client.post("/todos/projects/new", data={"title": title, "description": description, "target_date": "2026-08-20"}, follow_redirects=True)
    assert response.status_code == 200
    return response


def project_id(app):
    with app.app_context():
        return db.session.execute(db.select(Project.id)).scalar_one()


def add_project_task(client, project, text):
    return client.post(f"/todos/projects/{project}/tasks", data={"text": text}, follow_redirects=True)


def task_id(app, text):
    with app.app_context():
        return db.session.execute(db.select(Todo.id).where(Todo.text == text)).scalar_one()


def test_project_create_edit_and_duplicate_titles_are_safe(client, app):
    set_today(app)
    page = client.get("/todos/projects")
    assert page.status_code == 200 and b"New Project" in page.data and b"No projects yet" in page.data
    create_project(client, "Make a video")
    project = project_id(app)
    edited = client.post(f"/todos/projects/{project}/edit", data={"title": "Make a video", "description": "Edited description", "target_date": "2026-08-21"}, follow_redirects=True)
    assert b"Edited description" in edited.data
    create_project(client, "Make a video", "A separate project with the same title")
    with app.app_context():
        assert db.session.execute(db.select(Project).where(Project.title == "Make a video")).scalars().all().__len__() == 2


def test_project_tasks_do_not_appear_in_standalone_backlog(client, app):
    set_today(app)
    create_project(client)
    project = project_id(app)
    response = add_project_task(client, project, "Record video")
    assert b"Record video" in response.data and b"Project-only" in response.data and b"No tasks yet" not in response.data
    backlog = client.get("/todos/backlog")
    assert b"Record video" not in backlog.data
    with app.app_context():
        todo = db.session.get(Todo, task_id(app, "Record video"))
        assert todo.project_id == project and todo.current_location == "backlog"


def test_project_task_add_to_today_completes_same_task_and_shows_badge(client, app):
    set_today(app)
    create_project(client)
    project = project_id(app)
    add_project_task(client, project, "Record video")
    todo = task_id(app, "Record video")
    client.post(f"/todos/projects/{project}/tasks/{todo}/today")
    today = client.get("/todos/")
    assert b"Record video" in today.data and b"Project: Make a video" in today.data
    client.post(f"/todos/{todo}/complete", data={"return_to": "today"})
    with app.app_context():
        assert db.session.get(Todo, todo).status == "completed"
    detail = client.get(f"/todos/projects/{project}")
    assert b"1 of 1" in detail.data and b"Complete Project" in detail.data


def test_project_completion_rules_reopen_and_empty_project(client, app):
    set_today(app)
    create_project(client)
    project = project_id(app)
    assert client.post(f"/todos/projects/{project}/complete").status_code == 400
    add_project_task(client, project, "One task")
    todo = task_id(app, "One task")
    client.post(f"/todos/{todo}/complete", data={"return_to": f"project:{project}"})
    assert client.post(f"/todos/projects/{project}/complete").status_code == 302
    with app.app_context():
        assert db.session.get(Project, project).status == "completed"
    add_project_task(client, project, "New task")
    with app.app_context():
        reopened = db.session.get(Project, project)
        assert reopened.status == "active" and reopened.completed_at is None


def test_project_schedule_unschedule_and_ownership_validation(client, app):
    set_today(app)
    create_project(client)
    project = project_id(app)
    add_project_task(client, project, "Edit video")
    todo = task_id(app, "Edit video")
    client.post(f"/todos/projects/{project}/tasks/{todo}/schedule", data={"scheduled_date": "2026-08-02"})
    with app.app_context():
        saved = db.session.get(Todo, todo)
        assert saved.project_id == project and saved.scheduled_date == date(2026, 8, 2)
    client.post(f"/todos/projects/{project}/tasks/{todo}/unschedule")
    with app.app_context():
        assert db.session.get(Todo, todo).scheduled_date is None
    assert client.post(f"/todos/projects/{project}/tasks/{todo}/schedule", data={"scheduled_date": "bad"}).status_code == 400
    assert client.post(f"/todos/projects/99999/tasks/{todo}/today").status_code == 404


def test_archived_project_stops_carry_and_restores_project_only_tasks(client, app):
    set_today(app, date(2026, 8, 1))
    create_project(client)
    project = project_id(app)
    add_project_task(client, project, "Incomplete task")
    todo = task_id(app, "Incomplete task")
    client.post(f"/todos/projects/{project}/tasks/{todo}/schedule", data={"scheduled_date": "2026-07-31"})
    client.post(f"/todos/projects/{project}/archive")
    assert b"Incomplete task" not in client.get("/todos/").data
    with app.app_context():
        assert db.session.get(Project, project).status == "archived"
        assert db.session.get(Todo, todo).status == "archived"
    client.post(f"/todos/projects/{project}/restore")
    with app.app_context():
        restored = db.session.get(Todo, todo)
        assert db.session.get(Project, project).status == "active"
        assert restored.status == "active" and restored.current_location == "backlog" and restored.scheduled_date is None


def test_project_history_records_events_only_when_they_happen(client, app):
    set_today(app)
    create_project(client)
    project = project_id(app)
    add_project_task(client, project, "Thumbnail")
    todo = task_id(app, "Thumbnail")
    client.post(f"/todos/projects/{project}/tasks/{todo}/today")
    history = client.get("/todos/history?date=2026-07-31")
    assert b"Project activity" in history.data and b"Project task moved to Today" in history.data
    with app.app_context():
        assert db.session.execute(db.select(ProjectActivity).where(ProjectActivity.project_id == project)).scalars().all()


def test_project_migration_keeps_existing_tasks_standalone_and_reverses(tmp_path):
    database = tmp_path / "projects-migration.db"
    migration_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with migration_app.app_context():
        upgrade(directory=str(migrations), revision="6c7a8b9d0e12")
        db.session.execute(text("INSERT INTO todo (text, notes, is_completed, current_location, status, carry_count, created_at, updated_at) VALUES ('Standalone legacy', '', 0, 'backlog', 'active', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        db.session.commit()
        upgrade(directory=str(migrations), revision="head")
        row = db.session.execute(text("SELECT text, project_id FROM todo")).one()
        assert row == ("Standalone legacy", None)
        assert {"project", "project_activity"}.issubset(set(inspect(db.engine).get_table_names()))
        downgrade(directory=str(migrations), revision="6c7a8b9d0e12")
        assert "project_id" not in {column["name"] for column in inspect(db.engine).get_columns("todo")}
