# Exercise — Stage 4B

The user-facing section is **Exercise**. Its existing warm styling, dumbbell icon,
collapsed/expanded rail, mobile drawer and contextual home remain. The five tabs
are Today, Exercises, Runs, Templates and History. Established `/gym` URLs and
strength models deliberately remain stable. Exercise Today offers **Start strength
workout** and **Log a run**; a run and a strength workout can coexist on one date.

## Strength records and progress

Raw sets remain the source of truth. `ExerciseSet.weight_kg` is decimal kilograms;
reps are whole numbers. No personal-best table, flags, estimated 1RM or strength
score is stored. Empty occurrences do not count as logged sessions.

The summary shows last trained, sessions logged, heaviest weight, best reps at that
heaviest weight, and highest session volume, with occurrence/date links for weight
and volume. Archived exercise history remains included.

- **Weight PB:** maximum saved set weight, with best reps at that weight.
- **Rep PB:** more reps than previously saved at the exact same decimal weight.
  A newly used weight is not automatically a rep PB.
- **Volume PB:** greatest `sum(weight_kg * reps)` for one exercise occurrence.

Small labelled gold badges compare the current occurrence only with earlier
occurrences, ordered by workout date, start timestamp and occurrence ID. Strict
improvement is required. Ties and the first saved occurrence do not produce badges.
Future/backdated entries do not contaminate the comparison.

Existing Last Session, Heaviest Session, copy-previous, Weight Progression and
Session Volume are retained. Heaviest Session still breaks ties by max weight,
reps at that weight, then latest timestamp/occurrence. Historical workout detail
offers **Correct saved sets**; editing raw values recalculates summaries, PBs and
graphs on the next request. There are no cached/stale PB flags.

Today saves each set independently with CSRF protection. Removing an exercise with
saved sets requires confirmation. Removing one set compacts set numbers through a
temporary collision-free range, preserving remaining set order.

## Favourites and ordering

`Exercise.is_favorite` is a persistent boolean, default false. A star has an
accessible name and pressed state. Within each body part, active favourites appear
first, then non-favourites; archived items remain visible separately. Within each
subgroup the order is `sort_order`, name, ID. Discovery selectors use the same rule.

Up/down moves one position; Shift+up/down moves to the subgroup's top/bottom.
Movement is restricted to the same body part, favourite status and active status.
It never changes body part or rewrites workout history. The established button-only
Shift handler is reused, not a global Shift-click/new-window handler.

## Independent workout templates

`WorkoutTemplate` stores a user-supplied name and timestamps.
`WorkoutTemplateExercise` stores template/exercise IDs and order, unique per pair.
No weights, sets or target reps are stored in a template.

Templates support creation, renaming, confirmed deletion, adding/removing active
exercises and normal/Shift ordering. Starting a template creates independent
`WorkoutExercise` rows: there is no live template/workout relationship. Today can
remove, add and reorder exercises without changing the template. Later template
edits/deletion never change existing workouts.

Starting from a template is offered only when today's latest unfinished strength
workout is absent or empty. The server also rejects an attempted overwrite of a
nonempty workout. Archived template entries remain labelled in management, are
skipped with an explicit count when starting, and are never reactivated.

## Runs

`RunRoute` supplies stable route identity (display name, normalized unique name key,
timestamps, optional notes). Names collapse whitespace and use Unicode NFKC and
casefold for identity. Selecting an existing route or entering a case/spacing
variant reuses the same route. A new name takes priority over the selector.

`Run` stores route ID, local calendar date, optional time, decimal kilometres,
integer elapsed seconds, optional **plain-text** notes and timestamps. Date defaults
to the machine's local date, consistent with the existing Today feature. Tests may
inject `EXERCISE_TODAY`. No strength set/session is created by run logging.

Distance is 0.001–1,000 km with at most three decimal places. Elapsed time accepts
`m:ss` or `h:mm:ss`, requires valid seconds/minutes and a positive duration up to
seven days. All fields are validated before a route is created. Invalid submissions
retain the draft and do not leave orphan routes or partially edit a run.

Pace is derived using Decimal: `elapsed_seconds / distance_km`, displayed rounded
half-up to a whole second as `m:ss /km`. For example, **6.42 km in 31:18 = 4:53/km**.
Pace is never separately editable or stored.

### Running records

- Longest: greatest recorded distance, with route/date.
- Fastest average pace: lowest seconds/km; always show distance, duration, route
  and date so a short sprint is not presented as equivalent to a long run.
- Route PB: lowest average pace among runs sharing the stable route ID.
- Comparable route elapsed time is additionally shown only when the whole recorded
  distance range is within 1% of the shortest distance on that route.
- Fastest recorded 1/5/10 km uses **actual whole-run elapsed time**, never inferred
  splits. Inclusive qualifying windows are 0.980–1.020 km, 4.950–5.050 km, and
  9.900–10.100 km respectively. Fastest qualifying elapsed time wins; ties use the
  latest date/ID. No qualifying record means an explicit empty state.

New-run badges also compare only earlier chronological records and require strict
improvement; first-ever runs establish records without a shower of PB badges.

Weekly distance covers the current local Monday–Sunday calendar week; monthly
distance covers the current calendar month/year. Both sum exact decimal distance.
Run edits and confirmed POST+CSRF deletion immediately recalculate all totals,
records, route progress and graphs. Route identities remain when their last run is
deleted, making the route reusable.

### History and charts

Runs are newest first (date, optional time, ID). Detail includes all saved fields,
pace, PB feedback, correction and deliberate deletion. Route detail shows count,
most recent date, fastest pace, comparable elapsed time when meaningful, charts and
route history. History uses separate Strength/Runs controls.

Pace Progression shows human-readable min/km on its axis; **lower is faster**.
Distance by Run shows km. Every recorded run is a point. Hover, keyboard focus,
Enter/Space or touch reveals date, route, distance, elapsed duration and pace.
Tooltips use text nodes, not interpolated user HTML. Run lists provide textual
equivalents. Existing strength charts continue to show max weight, volume and sets.

## Architecture, search and future work

The original strength routes remain in `app/routes/gym.py`; additive management
routes live in `app/routes/exercise.py`. Calculations live in `app/gym.py` and
`app/running.py`. New routes are under `/gym/runs` and `/gym/templates`.

Universal Search retains its read-only, bounded architecture: it labels strength
results Exercise and searches named routes with `Exercise · Run route` results
linking to canonical route detail. It does not index individual numeric sets or
runs. There are now 13 bounded source queries rather than 12.

SQLite remains local-only at `127.0.0.1:5000`. No cloud deployment, integrations,
GPS, splits, coaching or social features were added. Independent normalized records
and derived values leave room for future authenticated mobile/cloud ownership.
True fastest rolling kilometre segments would require actual split/GPS data; the
present whole-run PBs deliberately make no such claim.

## Migration, backups and verification

Migration `e4b7a9c2d610` follows `0dd8dae16435`: one additive favourite column and
four new tables (`workout_template`, `workout_template_exercise`, `run_route`, `run`).
It does not rewrite old strength values. Existing favourite flags start false; no
sample runs, routes or templates are seeded into the real database.

`tests/exercise_release_audit.py prepare` creates a fresh validated rolling package,
validates the monthly package, performs separate non-destructive restore drills,
and saves per-table column/count/content hashes under ignored `instance/`.
After a separately authorized migration, `verify` compares every original field,
checks SQLite integrity/foreign keys, model/schema and migration head, empty new
tables, and creates/restores a fresh post-migration backup. Whole-database packages
automatically include the new tables; backup schedules and Task Scheduler are unchanged.

Focused coverage is in `tests/test_exercise_update.py`, alongside the retained
strength and search suites. `tests/exercise_browser_server.py` and
`tests/exercise_browser_check.cjs` verify fictional in-memory desktop and touch
flows, including 320/375/390/430 px views. They never open the real database.

### Stage 4B release verification

- 54 new focused tests passed; 105 combined Exercise/legacy strength/search tests
  passed after the final form refinements. Full regression: 359 passed (existing
  migration/ORM deprecation warnings remain).
- Desktop and touch at 320, 375, 390 and 430 px passed for the new flows, including
  template independence, strict PBs, run corrections/deletion and route search.
  The existing five-start-page Universal Search browser suite also passed.
- No browser console errors, failed assets or horizontal overflow were observed.
  Visual review additionally caught and prevented accidental rich-text conversion
  of plain run notes.
- All 23 pre-existing tables matched their original field/content hashes after
  migration. Strength counts were unchanged: 5 exercises, 3 sessions, 4 workout
  exercise occurrences, 12 sets. All four new tables started empty.
- Pre/post integrity was `ok`, foreign-key violations 0, schema differences 0.
  Fresh pre/post rolling backups and the monthly package validated; separate restore
  drills passed. Both existing scheduled-task definition hashes were unchanged.
- Python compilation, whitespace checks, eight original prototype hashes, privacy,
  secret, absolute-path and runtime/private-file scans passed. Runtime evidence,
  screenshots, database copies and backup packages stay outside Git.
- The normal hidden runner was restarted with one listener on `127.0.0.1:5000`;
  all seven Exercise list/history entry URLs returned HTTP 200. Disposable browser
  fixture servers were stopped after verification.
