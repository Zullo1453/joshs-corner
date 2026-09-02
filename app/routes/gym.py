from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..gym import exercise_volume, heaviest_occurrence, max_weight, parse_reps, parse_weight, previous_occurrence, progress_points, strength_summary, new_strength_pbs
from ..models import BODY_PARTS, Exercise, ExerciseSet, WorkoutExercise, WorkoutSession, WorkoutTemplate, utc_now
from ..running import local_today, all_runs


gym_bp = Blueprint("gym", __name__, url_prefix="/gym")


def _today_session() -> WorkoutSession | None:
    return db.session.scalar(
        select(WorkoutSession)
        .where(WorkoutSession.workout_date == local_today(), WorkoutSession.finished_at.is_(None))
        .options(joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.exercise), joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets))
        .order_by(WorkoutSession.started_at.desc(), WorkoutSession.id.desc())
    )


def _today_mutable(workout_exercise: WorkoutExercise) -> bool:
    return (
        workout_exercise.session.workout_date == local_today()
        and workout_exercise.session.finished_at is None
    )


def _grouped_active_exercises():
    exercises = db.session.scalars(
        select(Exercise).where(Exercise.active).order_by(Exercise.body_part, Exercise.is_favorite.desc(), Exercise.sort_order, Exercise.name, Exercise.id)
    ).all()
    return {body_part: [item for item in exercises if item.body_part == body_part] for body_part in BODY_PARTS}


@gym_bp.get("")
@gym_bp.get("/today")
def today():
    session = _today_session()
    cards = []
    if session:
        for occurrence in sorted(session.workout_exercises, key=lambda item: (item.sort_order, item.id)):
            cards.append(
                {
                    "occurrence": occurrence,
                    "volume": exercise_volume(occurrence),
                    "max_weight": max_weight(occurrence),
                    "previous": previous_occurrence(occurrence.exercise_id, session.id),
                    "pbs": new_strength_pbs(occurrence),
                }
            )
    return render_template(
        "gym/today.html", gym_page="today", session=session, cards=cards,
        grouped_exercises=_grouped_active_exercises(), exercise_volume=exercise_volume, max_weight=max_weight,
        templates=db.session.scalars(select(WorkoutTemplate).order_by(WorkoutTemplate.name, WorkoutTemplate.id)).all(),
    )


@gym_bp.post("/today/start")
def start_today():
    session = _today_session()
    if session is None:
        db.session.add(WorkoutSession(workout_date=local_today(), started_at=utc_now()))
        db.session.commit()
        flash("Today’s workout is ready.", "success")
    else:
        flash("Resumed today’s workout.", "info")
    return redirect(url_for("gym.today"))


@gym_bp.get("/exercises")
def exercises():
    all_exercises = db.session.scalars(select(Exercise).order_by(Exercise.active.desc(), Exercise.body_part, Exercise.is_favorite.desc(), Exercise.sort_order, Exercise.name, Exercise.id)).all()
    grouped = {body_part: [item for item in all_exercises if item.body_part == body_part] for body_part in BODY_PARTS}
    return render_template("gym/exercises.html", gym_page="exercises", grouped_exercises=grouped, body_parts=BODY_PARTS)


@gym_bp.post("/exercises")
def add_exercise():
    name, body_part = request.form.get("name", "").strip(), request.form.get("body_part", "")
    if not name or len(name) > 160:
        flash("Enter an exercise name up to 160 characters.", "error")
    elif body_part not in BODY_PARTS:
        flash("Choose a valid body part.", "error")
    else:
        highest = db.session.scalar(select(func.max(Exercise.sort_order)).where(Exercise.body_part == body_part))
        db.session.add(Exercise(name=name, body_part=body_part, sort_order=(highest or 0) + 1))
        db.session.commit()
        flash("Exercise added.", "success")
    return redirect(url_for("gym.exercises"))


@gym_bp.post("/exercises/<int:exercise_id>/edit")
def edit_exercise(exercise_id):
    exercise = db.get_or_404(Exercise, exercise_id)
    name, body_part = request.form.get("name", "").strip(), request.form.get("body_part", "")
    if not name or len(name) > 160 or body_part not in BODY_PARTS:
        flash("Use a valid exercise name and body part.", "error")
    else:
        exercise.name, exercise.body_part = name, body_part
        db.session.commit()
        flash("Exercise updated.", "success")
    return redirect(url_for("gym.exercises"))


@gym_bp.post("/exercises/<int:exercise_id>/archive")
def archive_exercise(exercise_id):
    exercise = db.get_or_404(Exercise, exercise_id)
    exercise.active = False
    db.session.commit()
    flash("Exercise archived. Its history is preserved.", "info")
    return redirect(url_for("gym.exercises"))


@gym_bp.post("/exercises/<int:exercise_id>/restore")
def restore_exercise(exercise_id):
    exercise = db.get_or_404(Exercise, exercise_id)
    exercise.active = True
    db.session.commit()
    flash("Exercise restored.", "success")
    return redirect(url_for("gym.exercises"))


@gym_bp.post("/today/exercises")
def add_to_today():
    session = _today_session()
    exercise = db.get_or_404(Exercise, request.form.get("exercise_id", type=int))
    if session is None:
        flash("Start today’s workout first.", "error")
    elif not exercise.active:
        flash("Archived exercises cannot be added to a new workout.", "error")
    elif any(item.exercise_id == exercise.id for item in session.workout_exercises):
        flash("That exercise is already in today’s workout.", "info")
    else:
        next_order = max((item.sort_order for item in session.workout_exercises), default=0) + 1
        db.session.add(WorkoutExercise(session=session, exercise=exercise, sort_order=next_order))
        db.session.commit()
        flash(f"{exercise.name} added to today’s workout.", "success")
    return redirect(url_for("gym.today"))


@gym_bp.post("/today/workout-exercises/<int:workout_exercise_id>/sets")
def add_set(workout_exercise_id):
    occurrence = db.get_or_404(WorkoutExercise, workout_exercise_id)
    if not _today_mutable(occurrence):
        abort(404)
    try:
        weight, reps = parse_weight(request.form.get("weight_kg", "")), parse_reps(request.form.get("reps", ""))
    except ValueError as error:
        flash(str(error), "error")
    else:
        db.session.add(ExerciseSet(workout_exercise=occurrence, set_number=len(occurrence.sets) + 1, weight_kg=weight, reps=reps))
        db.session.commit()
        flash("Set saved.", "success")
    return redirect(url_for("gym.today"))


@gym_bp.post("/sets/<int:set_id>/edit")
def edit_set(set_id):
    item = db.get_or_404(ExerciseSet, set_id)
    try:
        item.weight_kg, item.reps = parse_weight(request.form.get("weight_kg", "")), parse_reps(request.form.get("reps", ""))
        db.session.commit()
        flash("Set saved.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("gym.today") if _today_mutable(item.workout_exercise) else url_for("gym.workout_detail", session_id=item.workout_exercise.workout_session_id))


@gym_bp.post("/sets/<int:set_id>/remove")
def remove_set(set_id):
    item = db.get_or_404(ExerciseSet, set_id)
    occurrence = item.workout_exercise
    if not _today_mutable(occurrence):
        abort(404)
    remaining = [saved for saved in occurrence.sets if saved.id != item.id]
    db.session.delete(item)
    db.session.flush()
    # Move through a collision-free range before compacting the unique set numbers.
    for saved in remaining:
        saved.set_number = -saved.id
    db.session.flush()
    for index, saved in enumerate(remaining, 1):
        saved.set_number = index
    db.session.commit()
    flash("Set removed.", "info")
    return redirect(url_for("gym.today"))


@gym_bp.post("/today/workout-exercises/<int:workout_exercise_id>/copy-previous")
def copy_previous(workout_exercise_id):
    occurrence = db.get_or_404(WorkoutExercise, workout_exercise_id)
    if not _today_mutable(occurrence):
        abort(404)
    if occurrence.sets:
        flash("Previous sets were not copied because today already has saved sets.", "info")
    else:
        previous = previous_occurrence(occurrence.exercise_id, occurrence.workout_session_id)
        if previous is None:
            flash("There is no previous workout to copy.", "info")
        else:
            for index, source in enumerate(previous.sets, 1):
                db.session.add(ExerciseSet(workout_exercise=occurrence, set_number=index, weight_kg=source.weight_kg, reps=source.reps))
            db.session.commit()
            flash("Previous sets copied. They are now independent of history.", "success")
    return redirect(url_for("gym.today"))


@gym_bp.get("/exercises/<int:exercise_id>")
def exercise_detail(exercise_id):
    exercise = db.get_or_404(Exercise, exercise_id)
    points = progress_points(exercise.id)
    last = next((item for item in reversed([item for item in _occurrences_for_detail(exercise.id) if item.sets])), None)
    return render_template(
        "gym/exercise_detail.html", gym_page="exercises", exercise=exercise, last=last,
        heaviest=heaviest_occurrence(exercise.id), points=points, exercise_volume=exercise_volume,
        max_weight=max_weight,
        progress=strength_summary(exercise.id),
    )


def _occurrences_for_detail(exercise_id):
    return list(db.session.scalars(
        select(WorkoutExercise).join(WorkoutExercise.session).where(WorkoutExercise.exercise_id == exercise_id).options(joinedload(WorkoutExercise.session), joinedload(WorkoutExercise.sets)).order_by(WorkoutSession.started_at, WorkoutSession.id, WorkoutExercise.id)
    ).unique())


@gym_bp.get("/history")
def history():
    if request.args.get("kind") == "runs":
        return render_template("gym/run_history.html", gym_page="history", runs=all_runs())
    sessions = list(db.session.scalars(
        select(WorkoutSession).options(joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.exercise), joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets)).order_by(WorkoutSession.workout_date.desc(), WorkoutSession.started_at.desc(), WorkoutSession.id.desc())
    ).unique())
    sessions = [item for item in sessions if any(exercise.sets for exercise in item.workout_exercises)]
    return render_template("gym/history.html", gym_page="history", sessions=sessions, exercise_volume=exercise_volume, max_weight=max_weight)


@gym_bp.get("/history/<int:session_id>")
def workout_detail(session_id):
    session = db.session.scalar(select(WorkoutSession).where(WorkoutSession.id == session_id).options(joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.exercise), joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets)))
    if session is None:
        abort(404)
    return render_template("gym/workout_detail.html", gym_page="history", session=session, exercise_volume=exercise_volume, max_weight=max_weight)
