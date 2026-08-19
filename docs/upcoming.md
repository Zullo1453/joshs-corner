# Upcoming

Upcoming tracks events that happen on a date; it is independent from Deadlines and To-Dos. `UpcomingEvent` stores title, optional description, event date, optional event time, and standard timestamps.

`/upcoming` provides add, upcoming, past, detail, edit, and confirmed delete actions. Events require no completion action: they remain upcoming through their date and become Past the next local calendar day.

The Hub shows the next three events, including today. Status is derived by calendar date as Today, Tomorrow, or N days away. Same-date timed events sort before untimed events, then by creation timestamp and ID. Past events never appear in the Hub panel.

Upcoming uses the Hub’s antique-gold category alongside rose Deadlines and teal informational panels. Calendar sync, reminders, recurrence, and external notifications are explicitly deferred.
