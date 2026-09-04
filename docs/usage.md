# Intelligence → Usage

Usage is a read-only, local-only view at `/automations/usage`. It reports the current SQLite database size, the configured attachment upload directory, and Josh's Corner backup packages in the project `backups/rolling` and `backups/monthly` locations. The total intentionally excludes source code, Git data, dependencies, `.venv`, and unrelated folders.

The page also counts meaningful user records: journal entries, notes, To-Dos, projects, deadlines, upcoming events, media lists, exercise data, runs, and workout templates. It never displays file paths, user content, secrets, or environment values.

The Cloud section is a placeholder only: Supabase and Vercel are not connected and no provider requests are made. `UsageService.local_usage()` and `UsageService.database_counts()` keep the local summary separate so provider-specific adapters can be added after a future cloud migration.
