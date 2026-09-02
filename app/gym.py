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

def strength_summary(exercise_id, occurrences=None):
    """All summaries derive from saved sets, including archived exercises."""
    saved = [item for item in (occurrences if occurrences is not None else _occurrences(exercise_id)) if item.sets]
    if not saved:
        return dict(count=0, last=None, heaviest=None, weight=None, reps=0, volume=None)
    heaviest = max(saved, key=lambda item: (max_weight(item), reps_at_max_weight(item), item.session.started_at, item.id))
    return dict(count=len(saved), last=max(saved, key=occurrence_key), heaviest=heaviest,
                weight=max_weight(heaviest), reps=reps_at_max_weight(heaviest),
                volume=max(saved, key=lambda item: (exercise_volume(item), occurrence_key(item))))


def occurrence_key(item):
    return item.session.workout_date, item.session.started_at, item.id


def new_strength_pbs(occurrence):
    previous = [item for item in _occurrences(occurrence.exercise_id)
                if item.sets and occurrence_key(item) < occurrence_key(occurrence)]
    if not occurrence.sets or not previous:
        return []
    labels = []
    prior_weight = max(max_weight(item) for item in previous)
    if max_weight(occurrence) > prior_weight:
        labels.append("New weight PB")
    reps_by_weight = {}
    for item in previous:
        for saved_set in item.sets:
            weight = decimal_value(saved_set.weight_kg)
            reps_by_weight[weight] = max(reps_by_weight.get(weight, 0), saved_set.reps)
    current_reps = {}
    for saved_set in occurrence.sets:
        weight = decimal_value(saved_set.weight_kg)
        current_reps[weight] = max(current_reps.get(weight, 0), saved_set.reps)
    for weight, reps in sorted(current_reps.items()):
        if weight in reps_by_weight and reps > reps_by_weight[weight]:
            labels.append(f"New rep PB at {format_kg(weight)}")
    if exercise_volume(occurrence) > max(exercise_volume(item) for item in previous):
        labels.append("New volume PB")
    return labels


def move_in_group(items, item_id, action):
    """Caller supplies the exact ordering group; no other group is rewritten."""
    if action not in {"up", "down", "top", "bottom"}:
        raise ValueError("Choose a valid ordering action.")
    items = list(items)
    index = next((i for i, item in enumerate(items) if item.id == item_id), None)
    if index is None:
        raise ValueError("Item is not in this ordering group.")
    target = {"up": max(0, index - 1), "down": min(len(items) - 1, index + 1),
              "top": 0, "bottom": len(items) - 1}[action]
    items.insert(target, items.pop(index))
    for position, item in enumerate(items):
        item.sort_order = position
