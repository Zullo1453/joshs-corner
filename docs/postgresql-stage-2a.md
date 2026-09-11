# PostgreSQL compatibility — Online Stage 2A

Stage 2A makes Josh's Corner technically capable of selecting PostgreSQL while preserving its existing local SQLite behaviour. It creates no cloud resources, migrates no user data, changes no live schema, and does not alter attachment storage.

## Database and driver

With no `DATABASE_URL`, the application still opens `instance/joshs_corner.db`. `app.runtime` is the single database configuration boundary. It normalises provider-style `postgres://` and bare `postgresql://` URLs to `postgresql+psycopg://`, while leaving explicit driver URLs unchanged.

The project uses Psycopg 3 (`psycopg[binary]==3.3.5`) with SQLAlchemy 2.0.51. Psycopg 3 is SQLAlchemy's current PostgreSQL driver architecture and the binary distribution gives Windows and deployment installs a self-contained libpq implementation. SQLite remains available without PostgreSQL running locally.

PostgreSQL engine options are isolated from SQLite:

- connection health is checked before checkout;
- connections are recycled after 300 seconds;
- the application-side pool is conservatively limited to one connection with no overflow for short-lived serverless workers;
- Psycopg automatic prepared statements are disabled, which is required by transaction-mode poolers;
- SQLite retains Flask-SQLAlchemy's established engine defaults.

Flask-SQLAlchemy provides an application/request-scoped session and removes it when the application context ends. The app does not depend on a permanent worker, persistent in-process session state, or startup-time database work. `FLASK_SECRET_KEY` is also an environment boundary; the existing local development fallback remains for local use only.

The likely later runtime path is:

```text
Vercel Flask worker
        ↓
Supabase transaction pooler
        ↓
PostgreSQL
```

Stage 2B must confirm the real provider endpoints and settings before use. Migrations should use the direct database connection when reachable, not the transaction pooler.

## Universal Search

`PostgresSearchAdapter` implements database-side candidate filtering and the same score bands as local Search: exact title, title prefix, title contains, all title words, body phrase, and all combined words. It also provides date-title formatting, rich-text tag removal, common HTML entity decoding, punctuation/whitespace normalisation, full-width ASCII folding, `ß` folding, deterministic tie-breaking, play-log grouping, and the global result limit.

The adapter does not load the whole database into Python. It uses the same `UniversalSearchService.scope_statement()` ownership hook as SQLite; Stage 3 can add owner scoping there once, without accepting table names from clients. No embeddings, vector search, extensions, or semantic ranking were added.

All 13 Search sources compile for PostgreSQL. Exact live PostgreSQL result parity remains a Stage 2B execution test because no PostgreSQL service or container runtime was available on this machine.

## Models, migrations, and transactions

No migration revision was added and no revision ID changed. Existing Boolean server defaults were changed from SQLite-only `0/1` literals to SQLAlchemy `true()`/`false()` expressions, which compile to native PostgreSQL Boolean defaults and retain SQLite's `0/1` schema semantics.

The historical daily To-Do backfill was converted from a row-by-row Python result loop to equivalent set-based SQL. This preserves its SQLite outcome and allows Alembic to render a complete offline PostgreSQL build. Offline PostgreSQL SQL generation now reaches migration head `a9c4d7e1b250` from zero.

Models compile to PostgreSQL with native `DATE`, `TIME`, timezone-aware timestamp, Boolean, `NUMERIC(8,2)` strength-weight, and `NUMERIC(8,3)` run-distance types. Existing named unique, check, and foreign-key constraints are retained. Representative SQLite round trips cover `22.50` weights, `2.500` and `6.420` distances, true/false values, date-only fields, optional local time, and timestamps.

Recurring occurrence generation still treats the named rule/date unique constraint as authoritative. Each new occurrence now uses a savepoint; if another transaction wins the same insert, that one conflict does not roll back other dates being generated. Duplicate active workout sessions, exercise set-number collisions, and sort-order collisions need ownership-aware concurrency decisions and, where appropriate, schema constraints in Stage 3. No Stage 2A schema change was made for them.

## Local-only boundaries

SQLite PRAGMAs, custom Search functions, backup APIs, the local database path, and `LocalStorageBackend` remain SQLite/local only. App creation does not run backups. The dedicated backup scripts remain separate. Calendar dates keep their existing local meaning; Stage 3 must introduce an explicit Australia/Sydney or per-user timezone boundary without converting date-only fields into timestamps.

## Validation boundary

Stage 2A can prove PostgreSQL dialect compilation, driver loading, engine configuration, migration rendering, search-statement construction, model types/defaults, SQLite parity, and the full local regression suite. It cannot honestly prove real PostgreSQL connectivity, executed migrations, CRUD, constraint enforcement, transaction behaviour, or live Search output until Josh supplies an approved disposable Stage 2B project.

**REAL POSTGRES EXECUTION PENDING STAGE 2B.**