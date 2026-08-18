"""Derived Gym calculations. Raw sets remain the single source of truth."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from .extensions import db
from .models import ExerciseSet, WorkoutExercise, WorkoutSession


ZERO = Decimal("0")


def decimal_value(value) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))


def format_number(value) -> str:
    number = decimal_value(value)
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def format_kg(value) -> str:
    return f"{format_number(value)} kg"


def format_volume(value) -> str:
    return f"{format_number(value)} kg"


def set_summary(exercise_set: ExerciseSet) -> str:
    return f"{format_number(exercise_set.weight_kg)} × {exercise_set.reps}"


def exercise_volume(workout_exercise: WorkoutExercise) -> Decimal:
    return sum((decimal_value(item.weight_kg) * item.reps for item in workout_exercise.sets), ZERO)


def max_weight(workout_exercise: WorkoutExercise) -> Decimal | None:
    if not workout_exercise.sets:
        return None
    return max(decimal_value(item.weight_kg) for item in workout_exercise.sets)


def reps_at_max_weight(workout_exercise: WorkoutExercise) -> int:
    weight = max_weight(workout_exercise)
    if weight is None:
        return 0
    return max((item.reps for item in workout_exercise.sets if decimal_value(item.weight_kg) == weight), default=0)


def _occurrences(exercise_id: int) -> list[WorkoutExercise]:
    statement = (
        select(WorkoutExercise)
        .join(WorkoutExercise.session)
        .where(WorkoutExercise.exercise_id == exercise_id)
        .options(joinedload(WorkoutExercise.session), joinedload(WorkoutExercise.sets))
        .order_by(WorkoutSession.started_at, WorkoutSession.id, WorkoutExercise.id)
    )
    return list(db.session.scalars(statement).unique())


def previous_occurrence(exercise_id: int, current_session_id: int | None = None) -> WorkoutExercise | None:
    occurrences = _occurrences(exercise_id)
    if current_session_id is not None:
        occurrences = [item for item in occurrences if item.workout_session_id != current_session_id]
    return next((item for item in reversed(occurrences) if item.sets), None)


def heaviest_occurrence(exercise_id: int) -> WorkoutExercise | None:
    candidates = [item for item in _occurrences(exercise_id) if item.sets]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            max_weight(item),
            reps_at_max_weight(item),
            item.session.started_at,
            item.id,
        ),
    )


def progress_points(exercise_id: int) -> list[dict]:
    """One point per real exercise occurrence, including same-day duplicates."""
    points = []
    for occurrence in _occurrences(exercise_id):
        if not occurrence.sets:
            continue
        points.append(
            {
                "id": occurrence.id,
                "date": occurrence.session.workout_date.isoformat(),
                "started_at": occurrence.session.started_at.isoformat(),
                "max_weight": float(max_weight(occurrence)),
                "volume": float(exercise_volume(occurrence)),
                "sets": [set_summary(item) for item in occurrence.sets],
            }
        )
    return points


def parse_weight(value: str) -> Decimal:
    try:
        weight = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("Enter a valid weight in kilograms.") from None
    if not weight.is_finite() or weight < 0 or weight > Decimal("1000"):
        raise ValueError("Weight must be between 0 and 1,000 kg.")
    return weight.quantize(Decimal("0.01"))


def parse_reps(value: str) -> int:
    try:
        reps = int(value.strip())
    except (ValueError, AttributeError):
        raise ValueError("Enter whole-number reps.") from None
    if not 1 <= reps <= 1000:
        raise ValueError("Reps must be between 1 and 1,000.")
    return reps
