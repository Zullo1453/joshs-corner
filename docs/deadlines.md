# Deadline Centre

Deadlines are independent from To-Dos. The `Deadline` table stores title, optional description, due date, completion state, completion timestamp, standard timestamps, and an optional unique `source_journal_entry_id`. No Todo, project, reminder, or notification record is created.

`/deadlines` provides add, active, completed, reopen, and delete actions. `/deadlines/<id>` provides read-only details plus deliberate edit, complete/reopen, and confirmed-delete actions.

Active records sort by due date, then creation time and ID. The Hub preview supplies that urgency order and visually shows only the records that fit its fixed tile-height panel, including overdue records. Completed records never appear there.

A Deadline can optionally originate from a Journal entry. It remains a normal independent Deadline: editing, completing, reopening, or deleting it in Deadline Centre does not alter the Journal entry. Deleting it simply leaves the Journal entry without a Deadline link.

Status uses calendar-date subtraction: due today, singular/plural days left, or singular/plural days overdue. It is derived on every request. Completion removes the status from active views; reopening recalculates it immediately.

Future reminders or a deliberate To-Do relationship can be added later without merging the present data models.
