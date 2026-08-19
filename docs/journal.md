# Journal optional links

Journal entries stay ordinary by default. The optional **Add to** controls are both off for every new entry, so no classification, date extraction, reminder, calendar sync, or linked record is created unless the user explicitly selects it.

An entry can link to neither, a Deadline, an Upcoming event, or both. Deadline and Upcoming use separate concise titles and their own dates; an Upcoming time is optional. The Journal body is never copied into their description fields.

Each source relationship is optional and one-to-one: `Deadline.source_journal_entry_id` and `UpcomingEvent.source_journal_entry_id` are nullable, unique foreign keys with `ON DELETE SET NULL`. Re-saving an enabled link updates the same record instead of creating duplicates. Editing the Journal body does not change linked titles, dates, times, or descriptions.

Unticking an existing link requires explicit confirmation and then deletes that linked record while keeping the Journal entry. Deleting a Journal entry takes the safer path: its Deadline and/or Upcoming records remain as standalone records and their source links are cleared. Deleting a linked record from its own Centre likewise leaves the Journal entry untouched.
