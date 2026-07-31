from datetime import date, datetime, timedelta

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for
from sqlalchemy import or_

from ..extensions import db
from ..models import Todo, TodoActivity, utc_now


todos_bp = Blueprint("todos", __name__, url_prefix="/todos")
MAX_TASK_LENGTH = 300
ACTIVE = "active"
COMPLETED = "completed"
ARCHIVED = "archived"
BACKLOG = "backlog"
DATED = "dated"


@todos_bp.get("/")
def index():
    return render_today()


@todos_bp.get("/backlog")
def backlog():
    todos = db.session.execute(
        db.select(Todo)
        .where(Todo.current_location == BACKLOG, Todo.status == ACTIVE)
        .order_by(Todo.created_at.asc(), Todo.id.asc())
    ).scalars().all()
    return render_todos("backlog", backlog_todos=todos)


@todos_bp.get("/history")
def history():
    selected_date = parse_history_date(request.args.get("date"))
    activities = activities_for_date(selected_date)
    return render_todos(
        "history", selected_date=selected_date, history_activities=activities,
        previous_date=selected_date - timedelta(days=1), next_date=selected_date + timedelta(days=1),
        activity_description=activity_description,
    )



@todos_bp.post("/new")
@todos_bp.post("/today/new")
def create():
    text = normalise_task(request.form.get("text"))
    if text is None:
        return render_today(
            error=f"Tasks need between 1 and {MAX_TASK_LENGTH} characters.",
            draft=(request.form.get("text") or "")[:MAX_TASK_LENGTH],
            status=400,
        )
    today = local_today()
    todo = Todo(text=text, current_location=DATED, status=ACTIVE, scheduled_date=today, original_date=today)
    db.session.add(todo)
    db.session.flush()
    record_activity(todo, "created_today", destination_date=today)
    db.session.commit()
    return redirect(url_for("todos.index"))


@todos_bp.post("/backlog/new")
def create_backlog():
    text = normalise_task(request.form.get("text"))
    if text is None:
        todos = active_backlog()
        return render_todos(
            "backlog", backlog_todos=todos,
            error=f"Tasks need between 1 and {MAX_TASK_LENGTH} characters.",
            draft=(request.form.get("text") or "")[:MAX_TASK_LENGTH], status=400,
        )
    todo = Todo(text=text, current_location=BACKLOG, status=ACTIVE)
    db.session.add(todo)
    db.session.flush()
    record_activity(todo, "created_backlog")
    db.session.commit()
    return redirect(url_for("todos.backlog"))


@todos_bp.post("/<int:todo_id>/edit")
def edit(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    require_active(todo)
    text = normalise_task(request.form.get("text"))
    if text is None:
        abort(400)
    if todo.text != text:
        todo.text = text
        record_activity(todo, "edited", source_date=todo.scheduled_date, destination_date=todo.scheduled_date)
        db.session.commit()
    return redirect_for_view(request.form.get("return_to"), todo)


@todos_bp.post("/<int:todo_id>/complete")
def complete(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    require_active(todo)
    now = utc_now()
    todo.is_completed = True
    todo.completed_at = now
    todo.status = COMPLETED
    if todo.current_location == BACKLOG:
        todo.current_location = ARCHIVED
        todo.archived_at = now
    record_activity(todo, "completed", source_date=todo.scheduled_date, destination_date=todo.scheduled_date)
    db.session.commit()
    return redirect_for_view(request.form.get("return_to"), todo)


@todos_bp.post("/<int:todo_id>/restore")
@todos_bp.post("/<int:todo_id>/reopen")
def restore(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    if todo.status != COMPLETED:
        abort(400)
    todo.is_completed = False
    todo.completed_at = None
    todo.status = ACTIVE
    if todo.current_location == ARCHIVED:
        todo.current_location = BACKLOG
        todo.archived_at = None
    record_activity(todo, "reopened", destination_date=todo.scheduled_date)
    db.session.commit()
    return redirect_for_view(request.form.get("return_to"), todo)


@todos_bp.post("/<int:todo_id>/move-backlog")
def move_backlog(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    require_active(todo)
    if todo.current_location != DATED:
        abort(400)
    source = todo.scheduled_date
    todo.current_location = BACKLOG
    todo.scheduled_date = None
    record_activity(todo, "moved_to_backlog", source_date=source)
    db.session.commit()
    return redirect(url_for("todos.backlog"))


@todos_bp.post("/<int:todo_id>/move-today")
def move_today(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    require_active(todo)
    if todo.current_location != BACKLOG:
        abort(400)
    today = local_today()
    todo.current_location = DATED
    todo.scheduled_date = today
    todo.original_date = todo.original_date or today
    todo.carried_from_date = None
    record_activity(todo, "moved_to_today", destination_date=today)
    db.session.commit()
    return redirect(url_for("todos.index"))


@todos_bp.post("/<int:todo_id>/schedule")
def schedule(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    require_active(todo)
    destination = parse_schedule_date(request.form.get("scheduled_date"))
    source = todo.scheduled_date
    event = "scheduled" if todo.current_location == BACKLOG else "rescheduled"
    todo.current_location = DATED
    todo.scheduled_date = destination
    todo.original_date = todo.original_date or destination
    todo.carried_from_date = None
    record_activity(todo, event, source_date=source, destination_date=destination)    db.session.commit()
    return redirect_for_view(request.form.get("return_to"), todo)


@todos_bp.post("/<int:todo_id>/delete")
@todos_bp.post("/<int:todo_id>/archive")
def delete(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    if todo.status == ARCHIVED:
        abort(400)
    source = todo.scheduled_date
    todo.current_location = ARCHIVED
    todo.status = ARCHIVED
    todo.archived_at = utc_now()
    record_activity(todo, "archived", source_date=source)
    db.session.commit()
    return redirect_for_view(request.form.get("return_to"), todo)


def render_today(error=None, draft="", status=200):
    today = local_today()
    carry_forward(today)
    hide_completed = request.args.get("hide_completed") == "1"
    todos = db.session.execute(
        db.select(Todo)
        .where(Todo.current_location == DATED, Todo.scheduled_date == today, Todo.status.in_((ACTIVE, COMPLETED)))
        .order_by(Todo.status.desc(), Todo.carry_count.desc(), Todo.created_at.asc(), Todo.id.asc())
    ).scalars().all()
    active_todos = [todo for todo in todos if todo.status == ACTIVE]
    completed_todos = [todo for todo in todos if todo.status == COMPLETED]
    return render_todos(
        "today", today=today, active_todos=active_todos,
        completed_todos=[] if hide_completed else completed_todos,
        completed_count=len(completed_todos), hide_completed=hide_completed,
        error=error, draft=draft, status=status,
    )


def render_todos(view, status=200, **context):
    template_context = {
        "view": view,
        "max_task_length": MAX_TASK_LENGTH,
        "today": local_today(),
        "error": None,
        "draft": "",
        "active_todos": [],
        "completed_todos": [],
        "completed_count": 0,
        "backlog_todos": [],
        "history_activities": [],
        "format_todo_date": format_todo_date,
    }
    template_context.update(context)
    return render_template("todos/index.html", **template_context), status


def active_backlog():
    return db.session.execute(
        db.select(Todo).where(Todo.current_location == BACKLOG, Todo.status == ACTIVE)
    ).scalars().all()


def carry_forward(today):
    """Move each overdue active logical task directly to today once."""
    overdue = db.session.execute(
        db.select(Todo)
        .where(
            Todo.current_location == DATED,
            Todo.status == ACTIVE,
            Todo.is_completed.is_(False),
            Todo.archived_at.is_(None),
            Todo.scheduled_date < today,
        )
        .order_by(Todo.scheduled_date.asc(), Todo.id.asc())
    ).scalars().all()
    if not overdue:
        return
    for todo in overdue:
        source = todo.scheduled_date
        # The conditional update makes repeated/concurrent requests safe: once
        # another request has moved this logical task, this request has no row
        # to update and must not add a second audit event.
        updated = db.session.execute(
            db.update(Todo)
            .where(
                Todo.id == todo.id,
                Todo.current_location == DATED,
                Todo.status == ACTIVE,
                Todo.scheduled_date == source,
            )
            .values(scheduled_date=today, carried_from_date=source, carry_count=Todo.carry_count + 1)
            .execution_options(synchronize_session=False)
        )
        if updated.rowcount:
            record_activity(todo, "carried_forward", source_date=source, destination_date=today)
    db.session.commit()


def record_activity(todo, event_type, source_date=None, destination_date=None):
    db.session.add(TodoActivity(
        todo=todo, event_type=event_type, occurred_at=utc_now(),
        source_date=source_date, destination_date=destination_date,
    ))


def activity_description(activity):
    """Short, server-rendered labels keep the audit history understandable."""
    labels = {
        "created_today": "Added to Today",
        "created_backlog": "Added to Backlog",
        "edited": "Edited",
        "completed": "Completed",
        "reopened": "Reopened",
        "moved_to_backlog": "Moved to Backlog",
        "moved_to_today": "Moved to Today",
        "scheduled": "Scheduled",
        "rescheduled": "Rescheduled",
        "carried_forward": "Carried forward",
        "archived": "Archived",
    }
    return labels.get(activity.event_type, activity.event_type.replace("_", " ").capitalize())


def format_todo_date(value):
    return "" if value is None else f"{value.day} {value.strftime('%B %Y')}"


def activities_for_date(selected_date):
    activities = db.session.execute(
        db.select(TodoActivity)
        .where(or_(TodoActivity.source_date == selected_date, TodoActivity.destination_date == selected_date))
        .order_by(TodoActivity.occurred_at.desc(), TodoActivity.id.desc())
    ).scalars().all()
    same_day = db.session.execute(
        db.select(TodoActivity).order_by(TodoActivity.occurred_at.desc(), TodoActivity.id.desc())
    ).scalars().all()
    seen = {activity.id for activity in activities}
    activities.extend(activity for activity in same_day if activity.id not in seen and local_date(activity.occurred_at) == selected_date)
    return sorted(activities, key=lambda activity: (activity.occurred_at, activity.id), reverse=True)


def local_today():
    injected = current_app.config.get("TODOS_TODAY")
    if isinstance(injected, date):
        return injected
    if isinstance(injected, str):
        try:
            return date.fromisoformat(injected)
        except ValueError:
            pass
    return datetime.now().astimezone().date()


def local_date(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=utc_now().tzinfo)
    return value.astimezone().date()


def parse_history_date(value):
    if not value:
        return local_today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        abort(400)


def parse_schedule_date(value):
    try:
        selected = date.fromisoformat(value or "")
    except ValueError:
        abort(400)
    if selected < local_today():
        abort(400)
    return selected


def require_active(todo):
    if todo.status != ACTIVE or todo.current_location == ARCHIVED:
        abort(400)


def redirect_for_view(view, todo):
    if view == "backlog":
        return redirect(url_for("todos.backlog"))
    if view == "history":
        return redirect(url_for("todos.history", date=todo.scheduled_date or local_date(todo.completed_at or todo.updated_at)))
    return redirect(url_for("todos.index"))


def normalise_task(value):
    text = (value or "").strip()
    if not text or len(text) > MAX_TASK_LENGTH:
        return None
    return text
