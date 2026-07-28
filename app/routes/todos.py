from flask import Blueprint, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Todo, utc_now

todos_bp = Blueprint("todos", __name__, url_prefix="/todos")
MAX_TASK_LENGTH = 300


@todos_bp.get("/")
def index():
    return render_todos()


@todos_bp.post("/new")
def create():
    text = normalise_task(request.form.get("text"))
    if text is None:
        return render_todos(
            error=f"Tasks need between 1 and {MAX_TASK_LENGTH} characters.",
            draft=(request.form.get("text") or "")[:MAX_TASK_LENGTH],
            status=400,
        )

    db.session.add(Todo(text=text))
    db.session.commit()
    return redirect(url_for("todos.index"))


@todos_bp.post("/<int:todo_id>/complete")
def complete(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    if not todo.is_completed:
        todo.is_completed = True
        todo.completed_at = utc_now()
        db.session.commit()
    return redirect(url_for("todos.index", archive=1))


@todos_bp.post("/<int:todo_id>/restore")
def restore(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    if todo.is_completed:
        todo.is_completed = False
        todo.completed_at = None
        db.session.commit()
    return redirect(url_for("todos.index", archive=1))


@todos_bp.post("/<int:todo_id>/delete")
def delete(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    was_completed = todo.is_completed
    db.session.delete(todo)
    db.session.commit()
    parameters = {"archive": 1} if was_completed else {}
    return redirect(url_for("todos.index", **parameters))


def render_todos(error=None, draft="", status=200):
    active_todos = Todo.query.filter_by(is_completed=False).order_by(Todo.created_at.desc()).all()
    archived_todos = (
        Todo.query.filter_by(is_completed=True)
        .order_by(Todo.completed_at.desc(), Todo.id.desc())
        .all()
    )
    return (
        render_template(
            "todos/index.html",
            active_todos=active_todos,
            archived_todos=archived_todos,
            active_count=len(active_todos),
            archived_count=len(archived_todos),
            archive_open=request.args.get("archive") == "1",
            error=error,
            draft=draft,
            max_task_length=MAX_TASK_LENGTH,
        ),
        status,
    )


def normalise_task(value):
    text = (value or "").strip()
    if not text or len(text) > MAX_TASK_LENGTH:
        return None
    return text
