# Josh's Corner Online — Stage 2B Supabase setup

Stage 2B is the first external boundary. Do these steps only when Josh is present and has approved creation of a disposable staging project. The current SQLite database remains the live source of truth throughout.

## Josh's exact setup steps

1. Open the [Supabase dashboard](https://supabase.com/dashboard) and sign in or create Josh's own account. Do not authorise GitHub or another provider unless Josh chooses to.
2. In Josh's organisation, choose **New project**. Recommended name: **Josh's Corner Staging** (the visible product is not being renamed).
3. Create a strong database password and save it directly in Josh's password manager. Never paste it into source code, Git, screenshots, issue text, or chat.
4. Choose the Australian or nearest Australian region offered by the dashboard for the lowest practical latency. Stage 2B must record the exact region actually offered; do not guess it in advance.
5. Choose the plan Josh approves, review any price before accepting it, and create the project. Stop if billing or an unexpected paid add-on is requested.
6. Wait until the project reports healthy/ready. Do not create tables, enable Auth, add RLS policies, create Storage buckets, or import data yet.
7. Open the project's **Connect** dialog. Copy the exact **Direct connection** URI and the exact **Transaction pooler** URI shown there. Do not reconstruct the hostname, username, project reference, port, or password by hand.
8. In project settings, open the API keys page and record the **Project URL** plus the browser-safe **publishable key** (or legacy `anon` key if that is what the project displays). A service-role/secret key is not required for Stage 2B database validation.
9. Copy `.env.example` to `.env` in the project root. `.env` is already Git-ignored. Put only the currently tested database URI in `DATABASE_URL`; use the direct URI for the explicit migration rehearsal and the transaction-pooler URI for the later serverless-shaped runtime test. Put the project URL and publishable/anon key in their matching blank fields. Do not keep both database passwords in source or tracked documentation.
10. Confirm to Codex that the staging project is ready and that the values are stored locally in `.env`. Do not paste the values into chat. Stage 2B should first run a redacted connectivity check before any schema or data operation.

## Which connection is for what

Supabase's current guidance uses a direct connection for migrations, `pg_dump`, backup/restore, and other single-session administrative work. Its shared transaction pooler is intended for serverless/edge workers and normally uses port `6543`; it does not support prepared statements. Josh's Corner's PostgreSQL configuration already disables Psycopg automatic prepared statements and limits each worker's application pool conservatively.

The direct endpoint may require IPv6. If the development network cannot reach it, stop and use the exact Supabase-supported alternative agreed in Stage 2B; do not buy an IPv4 add-on or weaken network controls without Josh's approval.

## What Codex needs for Stage 2B

- Josh's confirmation that the disposable staging project may be used.
- `DATABASE_URL` stored locally with the direct URI for the migration rehearsal.
- The transaction-pooler URI available locally for a separate runtime test.
- The exact chosen region and project name, with secrets redacted.

The project URL and publishable/anon key may be collected now but are not needed for PostgreSQL schema/search validation. `SUPABASE_STORAGE_BUCKET` stays blank because cloud file migration is later. A Supabase service-role/admin secret must remain server-only if a later approved stage proves it unavoidable; normal user requests must not run wholesale as an unrestricted service role.

## Stage 2B stop gates

Before migration, Stage 2B must take and validate a fresh local backup, record live SQLite integrity/foreign keys/counts, agree an isolated synthetic-first migration plan, and confirm the target is the disposable staging project. No real Josh data should be copied until a separate explicit test-migration approval.

Do not create Vercel, deploy, enable Auth, add `user_id`, add profiles, add RLS, create or migrate Storage, replace the live database, sync PostgreSQL back into SQLite, or alter the Golden Snapshot as part of this checklist.

## Ready signal

The setup phase is ready when the dashboard reports healthy, both connection modes have been copied exactly into private local secret storage, `.env` is untracked, and Josh has explicitly authorised Stage 2B validation. Then the first engineering action is a **redacted direct-connection check against the empty disposable staging project**.