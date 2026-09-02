"""Stage 4B management routes; existing strength URLs remain on gym_bp."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from ..extensions import db
from ..gym import move_in_group
from ..models import Exercise, ExerciseSet, Run, RunRoute, WorkoutExercise, WorkoutSession, WorkoutTemplate, WorkoutTemplateExercise, utc_now
from ..running import all_runs, comparable_elapsed_best, local_today, run_pbs, run_points, run_summary, validated_run_values, route_progress, parse_distance
from .gym import _today_mutable, _today_session, _grouped_active_exercises

exercise_bp = Blueprint("exercise", __name__, url_prefix="/gym")


def template_by_id(template_id):
    template = db.session.scalar(select(WorkoutTemplate).where(WorkoutTemplate.id == template_id).options(
        selectinload(WorkoutTemplate.exercises).joinedload(WorkoutTemplateExercise.exercise)))
    if template is None:
        abort(404)
    return template


def valid_name():
    name = " ".join(request.form.get("name", "").split())
    if not name or len(name) > 160:
        abort(400, description="Enter a name up to 160 characters.")
    return name


def move(items, item_id):
    try:
        move_in_group(items, item_id, request.form.get("action", ""))
    except ValueError as error:
        abort(400, description=str(error))
    db.session.commit()


@exercise_bp.post("/exercises/<int:exercise_id>/favorite")
def favorite(exercise_id):
    exercise = db.get_or_404(Exercise, exercise_id)
    exercise.is_favorite = not exercise.is_favorite
    db.session.commit()
    return redirect(url_for("gym.exercises"))


@exercise_bp.post("/exercises/<int:exercise_id>/move")
def move_exercise(exercise_id):
    exercise = db.get_or_404(Exercise, exercise_id)
    items = db.session.scalars(select(Exercise).where(
        Exercise.body_part == exercise.body_part, Exercise.is_favorite == exercise.is_favorite,
        Exercise.active == exercise.active,
    ).order_by(Exercise.sort_order, Exercise.name, Exercise.id)).all()
    move(items, exercise.id)
    return redirect(url_for("gym.exercises"))


@exercise_bp.post("/today/workout-exercises/<int:occurrence_id>/move")
def move_workout_exercise(occurrence_id):
    occurrence = db.get_or_404(WorkoutExercise, occurrence_id)
    if not _today_mutable(occurrence):
        abort(404)
    move(sorted(occurrence.session.workout_exercises, key=lambda item: (item.sort_order, item.id)), occurrence.id)
    return redirect(url_for("gym.today"))


@exercise_bp.post("/today/workout-exercises/<int:occurrence_id>/remove")
def remove_workout_exercise(occurrence_id):
    occurrence = db.get_or_404(WorkoutExercise, occurrence_id)
    if not _today_mutable(occurrence):
        abort(404)
    if occurrence.sets and request.form.get("confirm") != "yes":
        abort(400, description="Confirm removing this exercise and its saved sets.")
    db.session.delete(occurrence)
    db.session.commit()
    return redirect(url_for("gym.today"))


@exercise_bp.get("/templates")
def templates():
    return render_template("gym/templates.html", gym_page="templates",
        templates=db.session.scalars(select(WorkoutTemplate).order_by(WorkoutTemplate.name, WorkoutTemplate.id)).all())


@exercise_bp.post("/templates")
def create_template():
    template = WorkoutTemplate(name=valid_name())
    db.session.add(template)
    db.session.commit()
    return redirect(url_for("exercise.template_detail", template_id=template.id))


@exercise_bp.get("/templates/<int:template_id>")
def template_detail(template_id):
    return render_template("gym/template_detail.html", gym_page="templates",
        template=template_by_id(template_id), grouped_exercises=_grouped_active_exercises())


@exercise_bp.post("/templates/<int:template_id>/rename")
def rename_template(template_id):
    template = template_by_id(template_id)
    template.name = valid_name()
    db.session.commit()
    return redirect(url_for("exercise.template_detail", template_id=template_id))


@exercise_bp.post("/templates/<int:template_id>/delete")
def delete_template(template_id):
    if request.form.get("confirm") != "yes":
        abort(400)
    db.session.delete(template_by_id(template_id))
    db.session.commit()
    return redirect(url_for("exercise.templates"))


@exercise_bp.post("/templates/<int:template_id>/exercises")
def add_template_exercise(template_id):
    template = template_by_id(template_id)
    exercise = db.get_or_404(Exercise, request.form.get("exercise_id", type=int))
    if not exercise.active:
        abort(400, description="Choose an active exercise.")
    if not any(item.exercise_id == exercise.id for item in template.exercises):
        position = max((item.sort_order for item in template.exercises), default=-1) + 1
        template.exercises.append(WorkoutTemplateExercise(exercise=exercise, sort_order=position))
        template.updated_at = utc_now()
        db.session.commit()
    return redirect(url_for("exercise.template_detail", template_id=template_id))


def template_item(template_id, item_id):
    template = template_by_id(template_id)
    item = next((item for item in template.exercises if item.id == item_id), None)
    if item is None:
        abort(404)
    return template, item


@exercise_bp.post("/templates/<int:template_id>/exercises/<int:item_id>/remove")
def remove_template_exercise(template_id, item_id):
    template, item = template_item(template_id, item_id)
    template.exercises.remove(item)
    template.updated_at = utc_now()
    db.session.commit()
    return redirect(url_for("exercise.template_detail", template_id=template_id))


@exercise_bp.post("/templates/<int:template_id>/exercises/<int:item_id>/move")
def move_template_exercise(template_id, item_id):
    template, item = template_item(template_id, item_id)
    template.updated_at = utc_now()
    move(sorted(template.exercises, key=lambda item: (item.sort_order, item.id)), item.id)
    return redirect(url_for("exercise.template_detail", template_id=template_id))


@exercise_bp.post("/today/from-template")
def start_template():
    template = template_by_id(request.form.get("template_id", type=int))
    session = _today_session()
    if session and session.workout_exercises:
        flash("Your workout already has exercises. Add or remove them individually.", "info")
        return redirect(url_for("gym.today"))
    if session is None:
        session = WorkoutSession(workout_date=local_today(), started_at=utc_now())
        db.session.add(session)
    skipped = 0
    for item in sorted(template.exercises, key=lambda item: (item.sort_order, item.id)):
        if item.exercise.active:
            session.workout_exercises.append(WorkoutExercise(exercise_id=item.exercise_id, sort_order=len(session.workout_exercises)))
        else:
            skipped += 1
    db.session.commit()
    flash(f"Started from {template.name}. This workout is an independent copy.", "success")
    if skipped:
        flash(f"{skipped} archived exercise{'s were' if skipped != 1 else ' was'} skipped.", "info")
    return redirect(url_for("gym.today"))


def render_runs(error=None, draft=None, editing=None):
    runs = all_runs()
    return render_template("gym/runs.html", gym_page="runs", runs=runs,
        summary=run_summary(runs), points=run_points(runs),
        routes=db.session.scalars(select(RunRoute).order_by(RunRoute.name_key)).all(),
        today=local_today(), draft=draft or {}, error=error, editing=editing)


@exercise_bp.get("/runs")
def runs():
    return render_runs()


@exercise_bp.post("/runs")
def create_run():
    try:
        values = validated_run_values(request.form)
        run = Run(**values)
        db.session.add(run)
        db.session.commit()
    except (ValueError, IntegrityError) as error:
        db.session.rollback()
        message = str(error) if isinstance(error, ValueError) else "That route was just created. Please try saving again."
        return render_runs(error=message, draft=request.form), 400
    return redirect(url_for("exercise.run_detail", run_id=run.id))


@exercise_bp.get("/runs/<int:run_id>")
def run_detail(run_id):
    runs = all_runs()
    run = next((item for item in runs if item.id == run_id), None)
    if run is None:
        abort(404)
    return render_template("gym/run_detail.html", gym_page="runs", run=run,
        pbs=run_pbs(run, runs), routes=db.session.scalars(select(RunRoute).order_by(RunRoute.name_key)).all(), error=None)


@exercise_bp.post("/runs/<int:run_id>/edit")
def edit_run(run_id):
    run = db.get_or_404(Run, run_id)
    try:
        values = validated_run_values(request.form)
        for key, value in values.items():
            setattr(run, key, value)
        db.session.commit()
    except (ValueError, IntegrityError) as error:
        db.session.rollback()
        message = str(error) if isinstance(error, ValueError) else "That route was just created. Please try again."
        return render_runs(error=message, draft=request.form, editing=run), 400
    return redirect(url_for("exercise.run_detail", run_id=run_id))


@exercise_bp.post("/runs/<int:run_id>/delete")
def delete_run(run_id):
    if request.form.get("confirm") != "yes":
        abort(400)
    db.session.delete(db.get_or_404(Run, run_id))
    db.session.commit()
    return redirect(url_for("exercise.runs"))


@exercise_bp.get("/runs/routes/<int:route_id>")
def route_detail(route_id):
    route = db.get_or_404(RunRoute, route_id)
    runs = all_runs(route.id)
    comparison = route_progress(route, runs)
    return render_template("gym/route_detail.html", gym_page="runs", route=route, runs=runs,
        summary=run_summary(runs), elapsed_best=comparable_elapsed_best(runs), points=run_points(runs),
        comparison=comparison, comparison_points=run_points(comparison['runs']))


@exercise_bp.get('/runs/progress')
def choose_route_progress():
    route = db.get_or_404(RunRoute, request.args.get('route_id', type=int))
    return redirect(url_for('exercise.route_detail', route_id=route.id))


@exercise_bp.post('/runs/routes/<int:route_id>/distance')
def update_route_distance(route_id):
    route = db.get_or_404(RunRoute, route_id)
    try:
        distance = parse_distance(request.form.get('distance_km'))
    except ValueError as error:
        flash(str(error), 'error')
    else:
        route.distance_km = distance
        db.session.commit()
        flash('Route distance saved. Actual run distances and times were not changed.', 'success')
    return redirect(url_for('exercise.route_detail', route_id=route.id))
