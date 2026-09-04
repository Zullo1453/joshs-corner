# Cloud portability groundwork (Online Stage 1)

Josh's Corner remains a private, local Flask application in this stage:

- SQLite remains the default database, at `instance/joshs_corner.db`.
- Uploads remain under `instance/uploads` and are served by `/attachments/<id>`.
- The Windows Task Scheduler backup task runs `scripts/backup_database.py`.
- The local server remains `127.0.0.1:5000`.

No cloud account, deployment, authentication system, database migration, or data
migration is part of this stage.

## Configuration and paths

`app.runtime` is the small configuration boundary. `configured_database_uri()`
uses the existing SQLite URL when `DATABASE_URL` is absent. A future host can
provide `DATABASE_URL`; Stage 1 only records that insertion point and does not
connect to PostgreSQL or add a PostgreSQL driver.

`RuntimePaths` categorises the current filesystem use:

| Category | Current location | Future hosting treatment |
| --- | --- | --- |
| Durable user data | SQLite database, uploads | PostgreSQL and object storage |
| Disposable reference cache | On This Day and Figure of the Day JSON caches | May be absent, regenerated, or use a managed cache |
| Local operational state | `backups/`, manifests, local server log | Outside Vercel runtime; local backup system remains local |
| Temporary processing | Backup/restore and image-processing temporary directories | Ephemeral storage is acceptable |

The cache services tolerate missing, unreadable, empty, or unwritable cache
files. They are never the only copy of Josh's data.

## Search boundary

`UniversalSearchService` owns product behaviour and its central
`scope_statement()` hook. A future authenticated ownership predicate belongs
there, once, rather than being scattered through every Search source.

SQLite-specific custom functions, `instr()` candidate matching, and ranking SQL
live in `SQLiteSearchAdapter`. The local adapter is selected only for a SQLite
dialect. Stage 2 needs a parity-tested `PostgresSearchAdapter` before a
PostgreSQL database can be used.

## Attachment storage boundary

Attachments still use stable database IDs in rich text, for example
`/attachments/42`; documents do not contain physical filesystem paths.
`LocalStorageBackend` preserves the existing generated filename, traversal
protection, image validation, EXIF correction, resizing, deletion, and serving
behaviour. A later Supabase Storage backend must preserve this attachment-ID
contract, metadata validation, and the application record. Phone images should
eventually use an authenticated/signed direct-upload workflow rather than
proxying large files through a serverless Flask request.

## Stateless startup and backups

`create_app()` now registers routes, extensions, configuration, and disposable
service interfaces only. It does not create, validate, prune, or copy durable
backups. Repeated worker startup is therefore safe.

The dedicated local backup script still runs the existing validated lifecycle:
rolling packages every three days (latest 10), monthly packages (latest 12),
checksums, integrity checks, restore support, and Usage reporting. Vercel must
not run this local rolling/monthly engine.

## Time and later concurrency work

Calendar features currently retain host-local date semantics; no dates were
converted to UTC in this stage. A later configuration boundary may select
Australia/Sydney or an authenticated user's timezone without changing stored
calendar-field meanings.

Recurring To-Dos retain their current lazy occurrence generation, FIFO
completion, history, aggregation, and uniqueness behaviour. Exercise session,
set-numbering, ordering, and autosave also remain unchanged. Stage 2/3 must add
idempotent conflict handling before simultaneous devices are supported.

## Stage 2 starting point

Use a disposable Supabase/PostgreSQL compatibility project to add and test:

1. a serverless-safe SQLAlchemy PostgreSQL connection and migration workflow;
2. a Search adapter with SQLite output/ranking parity;
3. single-user Supabase Auth, ownership fields, RLS, and multi-user-ready tests;
4. Supabase Storage plus signed/direct upload handling.

That work requires Josh to create or approve the Supabase project and provide
server-side configuration. Likely future configuration categories are
`DATABASE_URL`, a Flask production secret, Supabase URL, browser-safe Supabase
configuration, server-only Supabase credentials, storage configuration, and a
deployment version. Browser-safe values are not server secrets. A Supabase
service-role/admin credential must never appear in browser JavaScript, HTML,
static assets, a PWA manifest, or any frontend environment bundle.
