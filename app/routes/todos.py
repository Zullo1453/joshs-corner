import json
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for
from sqlalchemy import or_

from ..extensions import db
from ..models import Project, ProjectActivity, RecurrenceRule, Todo, TodoActivity, utc_now
from ..recurrence import active_recurring_tasks, complete_oldest, discard_oldest, summary


todos_bp = Blueprint("todos", __name__, url_prefix="/todos")
MAX_TASK_LENGTH = 300
MAX_PROJECT_TITLE_LENGTH = 200
MAX_PROJECT_DESCRIPTION_LENGTH = 2000
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
        .where(Todo.current_location == BACKLOG, Todo.status == ACTIVE, Todo.project_id.is_(None))
        .order_by(Todo.created_at.asc(), Todo.id.asc())
    ).scalars().all()
    scheduled_todos = db.session.execute(
        db.select(Todo)
        .where(
            Todo.current_location == DATED,
            Todo.status == ACTIVE,
            Todo.project_id.is_(None),
            Todo.scheduled_date > local_today(),
        )
        .order_by(Todo.scheduled_date.asc(), Todo.created_at.asc(), Todo.id.asc())
    ).scalars().all()
    return render_todos("backlog", backlog_todos=todos, scheduled_todos=scheduled_todos)


@todos_bp.get("/recurring")
def recurring():
    rules = db.session.execute(
        db.select(RecurrenceRule).order_by(RecurrenceRule.is_active.desc(), RecurrenceRule.updated_at.desc(), RecurrenceRule.id.desc())
    ).scalars().all()
    return render_todos("recurring", recurrence_rules=rules)


@todos_bp.get("/task/<int:todo_id>")
def task_detail(todo_id):
    """Read-only retrieval for any task state, without rollover or generation."""
    todo = db.get_or_404(Todo, todo_id)
    return render_todos("task_detail", selected_task=todo)


@todos_bp.post("/recurring/new")
def create_recurring():
    text = normalise_task(request.form.get("text"))
    repeat_type = (request.form.get("repeat_type") or "").strip()
    if text is None:
        return render_todos("recurring", recurrence_rules=[], error=f"Tasks need between 1 and {MAX_TASK_LENGTH} characters.", status=400)
    values = recurrence_values_from_form(text, repeat_type, local_today(), request.form.get("rollover_enabled") == "true")
    if values is None:
        return render_todos("recurring", recurrence_rules=[], error="Choose a repeat pattern, valid interval, and start date.", status=400)
    db.session.add(RecurrenceRule(**values))
    db.session.commit()
    return redirect(url_for("todos.recurring"))


@todos_bp.post("/recurrences/<int:rule_id>/edit")
def edit_recurring(rule_id):
    rule = db.get_or_404(RecurrenceRule, rule_id)
    text = normalise_task(request.form.get("text"))
    if text is None:
        abort(400)
    values = recurrence_values_from_form(text, (request.form.get("repeat_type") or "").strip(), local_today(), request.form.get("rollover_enabled") == "true")
    if values is None:
        abort(400)
    for key, value in values.items():
        setattr(rule, key, value)
    db.session.commit()
    return redirect(url_for("todos.recurring"))

@todos_bp.post("/recurrences/<int:rule_id>/complete")
def complete_recurring(rule_id):
    db.get_or_404(RecurrenceRule, rule_id)
    complete_oldest(rule_id)
    return redirect(url_for("todos.index"))


@todos_bp.post("/recurrences/<int:rule_id>/discard")
def discard_recurring(rule_id):
    db.get_or_404(RecurrenceRule, rule_id)
    discard_oldest(rule_id)
    return redirect(url_for("todos.index"))


@todos_bp.post("/recurrences/<int:rule_id>/stop")
def stop_recurring(rule_id):
    rule = db.get_or_404(RecurrenceRule, rule_id)
    rule.is_active = False
    db.session.commit()
    return redirect(url_for("todos.recurring"))

@todos_bp.get("/history")
def history():
    selected_date = parse_history_date(request.args.get("date"))
    activities = activities_for_date(selected_date)
    return render_todos(
        "history", selected_date=selected_date, history_activities=activities,
        previous_date=selected_date - timedelta(days=1), next_date=selected_date + timedelta(days=1),
        activity_description=activity_description,
        project_activity_description=project_activity_description,
        history_project_activities=project_activities_for_date(selected_date),
        rollover_disabled_todos=rollover_disabled_for_date(selected_date),
    )


@todos_bp.get("/projects")
def projects():
    show_archived = request.args.get("archived") == "1"
    statuses = (ACTIVE, COMPLETED, ARCHIVED) if show_archived else (ACTIVE, COMPLETED)
    items = db.session.execute(
        db.select(Project).where(Project.status.in_(statuses)).order_by(
            Project.status.desc(), Project.updated_at.desc(), Project.id.desc()
        )
    ).scalars().all()
    return render_todos("projects", projects=items, show_archived=show_archived, project_progress=project_progress)


@todos_bp.get("/projects/new")
def new_project():
    return render_todos("project_form", project=None, project_draft={"title": "", "description": "", "target_date": ""})


@todos_bp.post("/projects/new")
def create_project():
    values = project_values_from_form()
    if values is None:
        return render_todos("project_form", project=None, project_draft=project_draft(), error="A project title is required and descriptions must be under 2,000 characters.", status=400)
    project = Project(**values)
    db.session.add(project)
    db.session.flush()
    record_project_activity(project, "project_created")
    db.session.commit()
    return redirect(url_for("todos.project_detail", project_id=project.id))


@todos_bp.get("/projects/<int:project_id>")
def project_detail(project_id):
    project = db.get_or_404(Project, project_id)
    return render_project_detail(project)


@todos_bp.post("/projects/<int:project_id>/edit")
def edit_project(project_id):
    project = db.get_or_404(Project, project_id)
    if project.status == ARCHIVED:
        abort(400)
    values = project_values_from_form()
    if values is None:
        return render_project_detail(project, error="A project title is required and descriptions must be under 2,000 characters.", status=400)
    if any(getattr(project, key) != value for key, value in values.items()):
        for key, value in values.items():
            setattr(project, key, value)
        record_project_activity(project, "project_edited")
        db.session.commit()
    return redirect(url_for("todos.project_detail", project_id=project.id))


@todos_bp.post("/projects/<int:project_id>/tasks")
def add_project_task(project_id):
    project = db.get_or_404(Project, project_id)
    if project.status == ARCHIVED:
        abort(400)
    text = normalise_task(request.form.get("text"))
    if text is None:
        return render_project_detail(project, error=f"Tasks need between 1 and {MAX_TASK_LENGTH} characters.", status=400)
    reopened = project.status == COMPLETED
    if reopened:
        reopen_project(project, "project_reopened")
    todo = Todo(text=text, project=project, current_location=BACKLOG, status=ACTIVE)
    db.session.add(todo)
    db.session.flush()
    record_activity(todo, "project_task_added")
    record_project_activity(project, "project_task_added", todo=todo)
    db.session.commit()
    return redirect(url_for("todos.project_detail", project_id=project.id))


@todos_bp.post("/projects/<int:project_id>/tasks/<int:todo_id>/today")
def project_task_today(project_id, todo_id):
    project, todo = project_and_task_or_404(project_id, todo_id)
    require_project_task_active(project, todo)
    today = local_today()
    if todo.current_location == DATED and todo.scheduled_date == today:
        return redirect(url_for("todos.project_detail", project_id=project.id))
    source = todo.scheduled_date
    todo.current_location, todo.scheduled_date = DATED, today
    todo.original_date = todo.original_date or today
    todo.carried_from_date = None
    if source is None:
        todo.rollover_enabled = True
    record_activity(todo, "project_task_moved_to_today", source_date=source, destination_date=today)
    record_project_activity(project, "project_task_moved_to_today", todo=todo, source_date=source, destination_date=today)
    db.session.commit()
    return redirect(url_for("todos.project_detail", project_id=project.id))


@todos_bp.post("/projects/<int:project_id>/tasks/<int:todo_id>/schedule")
def project_task_schedule(project_id, todo_id):
    project, todo = project_and_task_or_404(project_id, todo_id)
    require_project_task_active(project, todo)
    destination = parse_schedule_date(request.form.get("scheduled_date"))
    source = todo.scheduled_date
    todo.current_location, todo.scheduled_date = DATED, destination
    todo.original_date = todo.original_date or destination
    todo.carried_from_date = None
    if source is None:
        todo.rollover_enabled = True
    event = "project_task_scheduled" if source is None else "project_task_rescheduled"
    record_activity(todo, event, source_date=source, destination_date=destination)
    record_project_activity(project, event, todo=todo, source_date=source, destination_date=destination)
    db.session.commit()
    return redirect(url_for("todos.project_detail", project_id=project.id))


@todos_bp.post("/projects/<int:project_id>/tasks/<int:todo_id>/unschedule")
def unschedule_project_task(project_id, todo_id):
    project, todo = project_and_task_or_404(project_id, todo_id)
    require_project_task_active(project, todo)
    source = todo.scheduled_date
    todo.current_location, todo.scheduled_date, todo.carried_from_date = BACKLOG, None, None
    record_activity(todo, "project_task_unscheduled", source_date=source)
    record_project_activity(project, "project_task_unscheduled", todo=todo, source_date=source)
    db.session.commit()
    return redirect(url_for("todos.project_detail", project_id=project.id))


@todos_bp.post("/projects/<int:project_id>/complete")
def complete_project(project_id):
    project = db.get_or_404(Project, project_id)
    eligible, _, _ = project_completion_state(project)
    if not eligible:
        return render_project_detail(project, error="Complete all remaining project tasks first.", status=400)
    project.status, project.completed_at = COMPLETED, utc_now()
    record_project_activity(project, "project_completed")
    db.session.commit()
    return redirect(url_for("todos.project_detail", project_id=project.id))


@todos_bp.post("/projects/<int:project_id>/reopen")
def reopen_project_route(project_id):
    project = db.get_or_404(Project, project_id)
    if project.status != COMPLETED:
        abort(400)
    reopen_project(project, "project_reopened")
    db.session.commit()
    return redirect(url_for("todos.project_detail", project_id=project.id))


@todos_bp.post("/projects/<int:project_id>/archive")
def archive_project(project_id):
    project = db.get_or_404(Project, project_id)
    if project.status == ARCHIVED:
        abort(400)
    now = utc_now()
    for todo in project.tasks:
        if todo.status == ACTIVE:
            source = todo.scheduled_date
            todo.status, todo.current_location, todo.scheduled_date, todo.archived_at = ARCHIVED, ARCHIVED, None, now
            record_activity(todo, "archived", source_date=source, metadata_json='{"project_archive": true}')
            record_project_activity(project, "project_task_archived", todo=todo, source_date=source)
    project.status, project.archived_at = ARCHIVED, now
    record_project_activity(project, "project_archived")
    db.session.commit()
    return redirect(url_for("todos.projects"))


@todos_bp.post("/projects/<int:project_id>/restore")
def restore_project(project_id):
    project = db.get_or_404(Project, project_id)
    if project.status != ARCHIVED:
        abort(400)
    for todo in project.tasks:
        latest_archive = next((item for item in sorted(todo.activities, key=lambda activity: activity.id, reverse=True) if item.event_type == "archived"), None)
        if todo.status == ARCHIVED and latest_archive and "project_archive" in latest_archive.metadata_json:
            todo.status, todo.current_location, todo.archived_at = ACTIVE, BACKLOG, None
            record_activity(todo, "project_task_restored")
    project.status, project.archived_at, project.completed_at = ACTIVE, None, None
    record_project_activity(project, "project_restored")
    db.session.commit()
    return redirect(url_for("todos.project_detail", project_id=project.id))


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
    todo = Todo(
        text=text, current_location=DATED, status=ACTIVE, scheduled_date=today, original_date=today,
        rollover_enabled=request.form.get("rollover_enabled") == "true",
    )
    db.session.add(todo)
    db.session.flush()
    record_activity(todo, "created_today", destination_date=today)
    db.session.commit()
    return redirect(url_for("todos.index"))


@todos_bp.post("/backlog/new")
def create_backlog():
    text = normalise_task(request.form.get("text"))
    schedule_value = (request.form.get("scheduled_date") or "").strip()
    if text is None:
        return render_backlog_form_error(
            f"Tasks need between 1 and {MAX_TASK_LENGTH} characters.",
            (request.form.get("text") or "")[:MAX_TASK_LENGTH], schedule_value,
        )
    try:
        destination = optional_schedule_date(schedule_value)
    except ValueError:
        return render_backlog_form_error(
            "Choose today or a future schedule date.", text, schedule_value,
        )

    todo = Todo(text=text, current_location=BACKLOG, status=ACTIVE, rollover_enabled=True)
    db.session.add(todo)
    db.session.flush()
    if destination is None:
        record_activity(todo, "created_backlog")
    else:
        apply_standalone_schedule(todo, destination)
        event = "created_scheduled_today" if destination == local_today() else "created_scheduled"
        record_activity(todo, event, destination_date=destination)
    db.session.commit()
    return redirect(url_for("todos.index" if destination == local_today() else "todos.backlog"))


@todos_bp.post("/<int:todo_id>/edit")
def edit(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    require_active(todo)
    text = normalise_task(request.form.get("text"))
    if text is None:
        abort(400)
    if todo.text != text:
        previous_text = todo.text
        todo.text = text
        record_activity(
            todo, "edited", source_date=todo.scheduled_date, destination_date=todo.scheduled_date,
            metadata_json=json.dumps({"previous_title": previous_text, "new_title": text}),
        )
        if todo.project:
            record_project_activity(todo.project, "project_task_edited", todo=todo, source_date=todo.scheduled_date, destination_date=todo.scheduled_date)
        db.session.commit()
    return redirect_for_view(request.form.get("return_to"), todo)


@todos_bp.post("/<int:todo_id>/rollover")
def set_rollover(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    require_active(todo)
    if todo.current_location != DATED:
        abort(400)
    enabled = parse_rollover_enabled(request.form.get("rollover_enabled"))
    if enabled is None:
        abort(400)
    if todo.rollover_enabled != enabled:
        previous = todo.rollover_enabled
        todo.rollover_enabled = enabled
        record_activity(
            todo, "rollover_changed", source_date=todo.scheduled_date, destination_date=todo.scheduled_date,
            metadata_json=json.dumps({"previous_value": previous, "new_value": enabled}),
        )
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
    if todo.project:
        record_project_activity(todo.project, "project_task_completed", todo=todo, source_date=todo.scheduled_date, destination_date=todo.scheduled_date)
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
    if todo.project:
        record_project_activity(todo.project, "project_task_reopened", todo=todo, destination_date=todo.scheduled_date)
    db.session.commit()
    return redirect_for_view(request.form.get("return_to"), todo)


@todos_bp.post("/<int:todo_id>/move-backlog")
def move_backlog(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    require_active(todo)
    if todo.current_location != DATED or todo.project_id is not None:
        abort(400)
    source = todo.scheduled_date
    todo.current_location = BACKLOG
    todo.scheduled_date = None
    record_activity(todo, "moved_to_backlog", source_date=source)
    if todo.project:
        record_project_activity(todo.project, "project_task_unscheduled", todo=todo, source_date=source)
    db.session.commit()
    return redirect(url_for("todos.backlog"))


@todos_bp.post("/<int:todo_id>/move-today")
def move_today(todo_id):
    todo = db.get_or_404(Todo, todo_id)
    require_active(todo)
    if todo.current_location != BACKLOG or todo.project_id is not None:
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
    if todo.current_location not in (BACKLOG, DATED) or todo.project_id is not None:
        abort(400)
    destination = parse_schedule_date(request.form.get("scheduled_date"))
    source = todo.scheduled_date
    from_backlog = todo.current_location == BACKLOG
    event = (
        "backlog_moved_to_today" if destination == local_today() else "backlog_scheduled"
    ) if from_backlog else "rescheduled"
    apply_standalone_schedule(todo, destination)
    record_activity(
        todo, event, source_date=source, destination_date=destination,
        metadata_json=json.dumps({"source": BACKLOG}) if from_backlog else None,
    )
    db.session.commit()
    if from_backlog and destination == local_today():
        return redirect(url_for("todos.index"))
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
    if todo.project:
        record_project_activity(todo.project, "project_task_archived", todo=todo, source_date=source)
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
        error=error, draft=draft, status=status, recurring_tasks=active_recurring_tasks(today),
    )


def render_todos(view, status=200, **context):
    template_context = {
        "view": view,
        "max_task_length": MAX_TASK_LENGTH,
        "today": local_today(),
        "error": None,
        "draft": "",
        "scheduled_draft": "",
        "active_todos": [],
        "completed_todos": [],
        "completed_count": 0,
        "backlog_todos": [],
        "scheduled_todos": [],
        "history_activities": [],
        "history_project_activities": [],
        "rollover_disabled_todos": [],
        "projects": [],
        "format_todo_date": format_todo_date,
        "recurrence_summary": summary,
        "recurrence_rules": [],
    }
    template_context.update(context)
    return render_template("todos/index.html", **template_context), status


def recurrence_values_from_form(text, repeat_type, today, rollover_enabled):
    """Return validated model values for a recurring task form submission."""
    if repeat_type not in {"daily", "weekly", "monthly"}:
        return None

    try:
        interval = max(1, int(request.form.get("repeat_interval") or 1))
        start_date = date.fromisoformat(request.form.get("repeat_start_date") or today.isoformat())
    except ValueError:
        return None

    values = {
        "text": text,
        "recurrence_type": repeat_type,
        "interval": interval,
        "start_date": start_date,
        "rollover_enabled": rollover_enabled,
    }
    if repeat_type == "weekly":
        try:
            weekdays = sorted({int(value) for value in request.form.getlist("repeat_weekdays")})
        except ValueError:
            return None
        if not weekdays or any(day < 0 or day > 6 for day in weekdays):
            return None
        values["weekdays_json"] = json.dumps(weekdays)
    elif repeat_type == "monthly":
        try:
            day_of_month = int(request.form.get("repeat_day_of_month") or start_date.day)
        except ValueError:
            return None
        if not 1 <= day_of_month <= 31:
            return None
        values["day_of_month"] = day_of_month

    return values

def active_backlog():
    return db.session.execute(
        db.select(Todo).where(Todo.current_location == BACKLOG, Todo.status == ACTIVE, Todo.project_id.is_(None))
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
            Todo.rollover_enabled.is_(True),
            ~Todo.project.has(Project.status == ARCHIVED),
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
                Todo.rollover_enabled.is_(True),
                Todo.scheduled_date == source,
            )
            .values(scheduled_date=today, carried_from_date=source, carry_count=Todo.carry_count + 1)
            .execution_options(synchronize_session=False)
        )
        if updated.rowcount:
            record_activity(todo, "carried_forward", source_date=source, destination_date=today)
    db.session.commit()


def record_activity(todo, event_type, source_date=None, destination_date=None, metadata_json=""):
    db.session.add(TodoActivity(
        todo=todo, event_type=event_type, occurred_at=utc_now(),
        source_date=source_date, destination_date=destination_date, metadata_json=metadata_json,
    ))


def record_project_activity(project, event_type, todo=None, source_date=None, destination_date=None, metadata_json=""):
    db.session.add(ProjectActivity(
        project=project, todo=todo, event_type=event_type, occurred_at=utc_now(),
        source_date=source_date, destination_date=destination_date, metadata_json=metadata_json,
    ))


def render_project_detail(project, error=None, status=200):
    tasks = db.session.execute(
        db.select(Todo).where(Todo.project_id == project.id).order_by(Todo.status.desc(), Todo.created_at.asc(), Todo.id.asc())
    ).scalars().all()
    eligible, completed, total = project_completion_state(project, tasks)
    return render_todos(
        "project_detail", project=project, project_tasks=tasks, error=error,
        project_progress=project_progress, project_completion_eligible=eligible,
        project_completed_count=completed, project_total_count=total, status=status,
    )


def project_values_from_form():
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    if not title or len(title) > MAX_PROJECT_TITLE_LENGTH or len(description) > MAX_PROJECT_DESCRIPTION_LENGTH:
        return None
    target_date = request.form.get("target_date") or ""
    if target_date:
        try:
            target_date = date.fromisoformat(target_date)
        except ValueError:
            return None
    else:
        target_date = None
    return {"title": title, "description": description, "target_date": target_date}


def project_draft():
    return {
        "title": request.form.get("title") or "",
        "description": request.form.get("description") or "",
        "target_date": request.form.get("target_date") or "",
    }


def project_and_task_or_404(project_id, todo_id):
    project = db.get_or_404(Project, project_id)
    todo = db.get_or_404(Todo, todo_id)
    if todo.project_id != project.id:
        abort(404)
    return project, todo


def require_project_task_active(project, todo):
    if project.status == ARCHIVED or todo.status != ACTIVE or todo.current_location == ARCHIVED:
        abort(400)


def project_completion_state(project, tasks=None):
    tasks = tasks if tasks is not None else project.tasks
    relevant = [todo for todo in tasks if todo.status != ARCHIVED]
    completed = sum(todo.status == COMPLETED for todo in relevant)
    return bool(relevant) and completed == len(relevant), completed, len(relevant)


def project_progress(project):
    _, completed, total = project_completion_state(project)
    return {"completed": completed, "total": total, "percent": round((completed / total) * 100) if total else 0}


def reopen_project(project, event_type):
    project.status, project.completed_at = ACTIVE, None
    record_project_activity(project, event_type)


def activity_description(activity):
    """Short, server-rendered labels keep the audit history understandable."""
    labels = {
        "created_today": "Added to Today",
        "created_backlog": "Added to Backlog",
        "created_scheduled_today": "Created and scheduled for Today",
        "created_scheduled": "Created and scheduled",
        "edited": "Edited",
        "completed": "Completed",
        "reopened": "Reopened",
        "moved_to_backlog": "Returned to Backlog",
        "moved_to_today": "Moved to Today",
        "backlog_moved_to_today": "Moved from Backlog to Today",
        "backlog_scheduled": "Scheduled from Backlog",
        "scheduled": "Scheduled",
        "rescheduled": "Rescheduled",
        "carried_forward": "Carried forward",
        "rollover_changed": "Rollover setting changed",
        "archived": "Archived",
    }
    return labels.get(activity.event_type, activity.event_type.replace("_", " ").capitalize())


def project_activity_description(activity):
    labels = {
        "project_created": "Project created",
        "project_edited": "Project edited",
        "project_completed": "Project completed",
        "project_reopened": "Project reopened",
        "project_archived": "Project archived",
        "project_restored": "Project restored",
        "project_task_added": "Project task added",
        "project_task_edited": "Project task edited",
        "project_task_moved_to_today": "Project task moved to Today",
        "project_task_scheduled": "Project task scheduled",
        "project_task_rescheduled": "Project task rescheduled",
        "project_task_unscheduled": "Project task returned to project",
        "project_task_completed": "Project task completed",
        "project_task_reopened": "Project task reopened",
        "project_task_archived": "Project task archived",
        "project_task_restored": "Project task restored",
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


def project_activities_for_date(selected_date):
    activities = db.session.execute(
        db.select(ProjectActivity)
        .where(or_(ProjectActivity.source_date == selected_date, ProjectActivity.destination_date == selected_date))
        .order_by(ProjectActivity.occurred_at.desc(), ProjectActivity.id.desc())
    ).scalars().all()
    same_day = db.session.execute(
        db.select(ProjectActivity).order_by(ProjectActivity.occurred_at.desc(), ProjectActivity.id.desc())
    ).scalars().all()
    seen = {activity.id for activity in activities}
    activities.extend(activity for activity in same_day if activity.id not in seen and local_date(activity.occurred_at) == selected_date)
    return sorted(activities, key=lambda activity: (activity.occurred_at, activity.id), reverse=True)


def rollover_disabled_for_date(selected_date):
    return db.session.execute(
        db.select(Todo)
        .where(
            Todo.current_location == DATED,
            Todo.status == ACTIVE,
            Todo.is_completed.is_(False),
            Todo.scheduled_date == selected_date,
            Todo.rollover_enabled.is_(False),
        )
        .order_by(Todo.updated_at.desc(), Todo.id.desc())
    ).scalars().all()


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
        selected = optional_schedule_date(value)
    except ValueError:
        abort(400)
    if selected is None:
        abort(400)
    return selected


def optional_schedule_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        selected = date.fromisoformat(value)
    except ValueError:
        raise ValueError from None
    if selected < local_today():
        raise ValueError
    return selected


def apply_standalone_schedule(todo, destination):
    todo.current_location = DATED
    todo.scheduled_date = destination
    todo.original_date = todo.original_date or destination
    todo.carried_from_date = None


def render_backlog_form_error(error, draft, scheduled_draft):
    return render_todos(
        "backlog", backlog_todos=active_backlog(),
        error=error, draft=draft, scheduled_draft=scheduled_draft, status=400,
    )


def parse_rollover_enabled(value):
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def require_active(todo):
    if todo.status != ACTIVE or todo.current_location == ARCHIVED:
        abort(400)


def redirect_for_view(view, todo):
    if view and view.startswith("project:"):
        try:
            project_id = int(view.split(":", 1)[1])
        except ValueError:
            abort(400)
        if todo.project_id != project_id:
            abort(400)
        return redirect(url_for("todos.project_detail", project_id=project_id))
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
