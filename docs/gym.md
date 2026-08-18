# Gym

Gym is local-only and stores raw exercises, workouts, and individual sets in SQLite. `Exercise` records have a body part, stable sort order, and archive flag. `WorkoutSession` keeps the date and timestamps; `WorkoutExercise` associates an exercise with one occurrence; `ExerciseSet` stores decimal kilograms and whole reps.

Routes: `/gym` (Today), `/gym/exercises`, `/gym/exercises/<id>`, `/gym/history`, and `/gym/history/<id>`.

Today resumes the latest unfinished workout for the current date. Each set is saved through its own CSRF-protected request. An exercise can copy the most recent earlier occurrence only while it has no current sets; copied sets are new independent records.

Volume is derived as `sum(weight_kg * reps)`. Max weight is the greatest set weight in an occurrence. Previous session is the most recent earlier occurrence with saved sets. Heaviest Session is selected by highest max weight, then most reps at that weight, then most recent timestamp.

Each exercise page has one point per occurrence: Weight Progression uses max weight, and Session Volume uses derived volume. Dates remain individual points even when labels are thinned. Hover, focus, or tap a point to see its sets.

Archived exercises remain in history and progress charts but cannot be added to a new workout. The responsive card and set-row layout reflows at narrow widths. Future cloud/multi-user work can add ownership to these independent tables without storing calculated values or rebuilding historical raw sets.
