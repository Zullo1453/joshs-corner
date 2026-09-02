# Stage 5A — Universal Search

Universal Search retrieves local records and opens their existing views. It does
not execute commands, save queries, call external search services, or change data.

## Architecture audit and decisions

The pre-change audit covered all models and their deletion/archive semantics,
module detail routes, the shared base template and navigation rail, the rich-text
sanitizer/preview helper, editor shortcuts and unsaved-change guards, module
partial navigation, the hidden server runner, migrations, backups, and existing
regression/prototype checks.

Findings that shaped the implementation:

- Existing sidebar modules use canonical full-page URLs with selected-record
  parameters. Their `/detail/<id>` routes return fragments, not complete pages.
  Search therefore uses the full-page URLs with no inherited sidebar filters.
- Partial navigation is scoped to clicks inside module sidebars. Global rail
  links already use ordinary browser navigation. Search uses the same real-link
  behavior, preserving browser history and existing beforeunload protections.
- Today performs lazy recurrence generation and rollover. Search must not call
  those functions. A small read-only `/todos/task/<id>` view supplies a reliable
  destination for tasks in any state without lifecycle writes.
- ReadingItem has no author column. Existing titles/notes remain searchable,
  including authors written in notes; no field or migration was added.
- Learning lessons have no independent destination. Learning search is deferred,
  as permitted by the brief, rather than creating a new section.
- The current rich-text editor has image-delete shortcuts but no custom Ctrl+K
  handler. Search nevertheless leaves inputs, selects, textareas and editable
  content alone to preserve browser/editor behavior and selections.

### Service and transport

`app/search.py` contains `UniversalSearchService`, a fixed allowlist of sources,
normalization, SQL candidate filtering and ranking, snippets, and canonical links.
`scope_statement()` is the central insertion point for future ownership filters.
The client cannot choose models or fields.

The service uses a separate SQLAlchemy Core connection and returns scalar rows:
no ORM autoflush, relationship traversal, cached record objects, or N+1 queries.
Each non-empty search executes 12 bounded SELECTs. Empty/one-character queries
execute none. Results are capped at 40 globally and 40 per source before merging.
Play-log candidates are ranked once per parent game with a SQL window function;
a matching review and multiple sessions yield one game result.

SQLite connection-local functions normalize text and dates while the database
filters and orders candidates. They are registered for a request and removed
afterwards. A bounded request-local text cache avoids repeatedly parsing the same
HTML inside SQL expressions. Nothing is persisted: there are no search tables,
indexes, triggers, schema changes, or migrations.

`POST /search` accepts only JSON `{"query": "..."}`, requires the existing CSRF
protection, and limits queries to 200 characters and request bodies to 4 KB.
Although POST is used, the operation is strictly read-only. Using a request body
keeps terms out of browser history, request URLs, and ordinary access logs.
Responses use `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.
Neither analytics nor query logging is added.

The internal result carries type, ID, title, subtitle, snippet, status, score,
destination, date, and a recency tie-breaker. Public JSON omits the internal ID,
score and recency.

Database failures are reported per source. Production responses retain other
results and tell the user that some sections are unavailable. Logs contain only
the source name and exception class, never SQL parameters or query text.
Testing mode re-raises the error; unrelated programmer errors are not swallowed.

## Supported fields and destinations

| Type | Fields | Canonical destination |
| --- | --- | --- |
| Journal | Plain-text body; ISO, numeric, long/short month and weekday date metadata | Exact journal date |
| General Notes | Title, plain-text body | Notes with exact note_id |
| To-Dos | Task text and plain-text notes | Read-only exact task view |
| Recurring To-Dos | Schedule task text | Recurring tab anchored to exact rule |
| Projects | Title, description | Exact project view |
| Deadlines | Title, description | Exact deadline detail |
| Upcoming | Title, description | Exact event detail |
| Game Journal | Game title, platform, review; play-entry title/body | Exact game, with Play Log anchor where relevant |
| Watchlist | Title, genre, media type, recommendation note, review | Watchlist with exact item_id |
| Reading List | Title, format, book type, notes | Reading with exact book_id |
| Gym | Exercise name, body part | Exact exercise/progress page |

Completed/archived tasks and projects, completed deadlines, past events, stopped
recurrence rules, and archived exercises remain retrievable and labelled.
Recurring schedules are grouped rather than returning every occurrence.
Physically deleted records cannot be returned because each search reads current
tables. The existing To-Do `delete` route is an alias for archiving; these retained
records are therefore labelled Archived, consistent with the app's lifecycle.

Excluded: Learning (deferred), numeric workout sets, Weather, Currency, Health,
backups, settings, migrations, attachments and runtime/private files.
No OCR or image-attribute indexing is performed.

## Matching, ranking, and snippets

Queries use Unicode NFKC normalization, casefolding, repeated-whitespace
normalization, and straightforward punctuation separation. For example,
`CBA-GradFest` and `CBA GradFest` match the same text. All query terms must be
present somewhere in the searched title/body; partial single-word matches do not
crowd out a multi-word search.

SQL ranking, highest first:

1. Exact normalized title.
2. Title starts with the full query.
3. Title contains the full query.
4. Title contains every query term.
5. Body contains the full query.
6. All terms occur across title and body.

Ties use recent updates, then stable type and record ID ordering. The UI groups
the capped results by type in first-ranked-group order, retaining ranking within
each group. Displayed counts describe returned results, not unbounded totals.

Rich text uses the existing `rich_text_preview` conversion with a sufficiently
large limit for matching; the sanitizer is unchanged. Block separators and
entities become readable text. Tags and image/link attributes do not become
searchable content. Snippets are at most 160 characters and clipped near a match.
Result strings are inserted with DOM `textContent`, never interpolated into HTML.
Literal user-written angle brackets remain harmless text.

## Interface and navigation

A magnifying-glass button appears below the section links, outside the section
navigation group. It uses the rail's 38px icon wrapper, with no section active
state, and works in the collapsed rail, expanded rail, and mobile drawer.

The shared base template includes one native modal dialog. Ctrl+K or Cmd+K opens
it when focus is outside an editor, or the user can click/tap Search from anywhere.
Focus enters the field immediately. Escape/Close clears the query, cancels pending
work, removes the scroll lock, and restores the original focus. Escape inside
Search does not also close the underlying navigation drawer.

The field is an accessible combobox with a grouped result list and live status.
Arrow keys change its active descendant; Enter follows that result's real link.
Tab also reaches individual result links. The native modal supplies focus
containment and makes the underlying document inert.

Search waits 180 ms after typing, cancels old requests, and rejects stale responses
with a sequence counter. Empty, short, no-results, loading and failure states are
explicit. The dialog has a scrolling result area, readable rows, 44px controls,
and dynamic viewport sizing for mobile keyboards.

Search adds no history entries for opening/closing. Ordinary result links navigate
in the current window; standard modifier-click behavior remains available.
No window.open call, custom router, cross-module DOM replacement, or partial-nav
interception is introduced. Existing dark first-paint styling remains in place.

## Verification and bug audit

Automated contract tests cover every listed source, secondary fields, exact
destinations, statuses, rich text/lists/quotes/links/images/entities, Unicode,
punctuation, minimum length, deterministic ranking, grouping, deletion, current
reads, CSRF, strict payloads, bounded results, SELECT-only execution and per-source
failure/privacy behavior.

The isolated performance fixture has 1,513 records: 501 journal entries,
501 notes, 501 tasks, and representative other records including game play logs.
Five measured endpoint calls took approximately 51–79 ms locally, including SQL,
normalization, snippets and JSON. The fixture is in memory and never touches the
live database. These are local measurements, not a performance guarantee.

Browser verification uses a fictional in-memory app on 127.0.0.1:5011 with
offline data services and a separate headless browser profile. The normal Browser
tool could not start because of the environment's sandbox-helper failure; the
available local Playwright/Chrome runtime was used instead.

Verified from Hub, Journal, To-Dos, Intelligence and Gym: keyboard opening, focused
input, cross-module results, exact Note navigation and Back. Additional checks
cover click and Enter, Up/Down, Ctrl+K and Cmd+K, Escape, repeated opening,
rapid typing, empty/no-results/200-character input, literal XSS-looking titles,
focus containment/return, expanded-rail behavior, Notes partial navigation,
unsaved-editor navigation warnings, and POST-only query transport.

Touch contexts at 320, 375, 390 and 430px passed search opening, result scrolling,
close/focus return, and exact result taps. Reducing viewport height to 390px
simulated keyboard space. No horizontal overflow or console errors was observed.
Actual physical-device keyboard behavior remains a manual-device check.

Release verification: 44 focused Search tests and the full 305-test suite passed.
Python compilation passed. Prototype hashes passed as part of the full suite.
The live database matched model metadata with zero schema differences, SQLite
integrity was `ok`, and the foreign-key check found zero violations. Migration
head stayed `0dd8dae16435`; no migration was run. Latest rolling/monthly packages
validated. Three live read-only searches returned results in approximately
35–67 ms. The database bytes, schema fingerprint and row counts were unchanged,
and the appended server log contained none of those query terms.

Risk findings:
- N+1/stale objects: bounded Core SELECTs and fresh rows; no lazy relationships.
- Unsafe HTML/XSS: unchanged sanitizer, plain-text conversion, DOM text nodes.
- Duplicate parents: SQL groups play logs; service merges matching parent results.
- Archived/deleted content: current tables plus explicit lifecycle labels.
- Shortcut collisions: editable controls retain their shortcuts.
- Navigation/Back: existing canonical URLs and ordinary links; no parallel router.
- Focus/scroll: native modal, focused input, Escape isolation, restoration and cleanup.
- Privacy: queries stay in POST bodies and memory; no query logs, analytics or index.
- Real data: release audit fingerprints the live DB and verifies unchanged bytes,
  schema and row counts around read-only live smoke searches.

## Future boundaries

Direct querying was sufficient for this dataset, so FTS5 was deliberately
deferred. That avoids index synchronization, stale indexes, triggers, and migration
complexity. A future hosted/PostgreSQL version can apply ownership restrictions
centrally and consider PostgreSQL full-text or trigram search only after measuring
a need; semantic search is a separate future decision.

Stage 5B may eventually add explicit commands such as `> New note`,
`> Add deadline`, `> Add event`, or `> Start workout`. Stage 5A contains no command
actions, AI, embeddings, external search, or search analytics.
