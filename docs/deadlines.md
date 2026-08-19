# Deadline Centre

Deadlines are independent from To-Dos. The `Deadline` table stores title, optional description, due date, completion state, completion timestamp, and standard timestamps. No Todo, project, reminder, or notification record is created.

`/deadlines` provides add, active, completed, reopen, and delete actions. `/deadlines/<id>` provides read-only details plus deliberate edit, complete/reopen, and confirmed-delete actions.

Active records sort by due date, then creation time and ID. The Hub shows the first three active records by that same query, including overdue records. Completed records never appear there.

Status uses calendar-date subtraction: due today, singular/plural days left, or singular/plural days overdue. It is derived on every request. Completion removes the status from active views; reopening recalculates it immediately.

Future reminders or a deliberate To-Do relationship can be added later without merging the present data models.
