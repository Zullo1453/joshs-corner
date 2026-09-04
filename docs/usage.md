# Intelligence → Usage

Usage is a read-only, local-only view at `/automations/usage`. It reports the current SQLite database size, the configured attachment upload directory, and Josh's Corner backup storage. The total intentionally excludes source code, Git data, dependencies, `.venv`, and unrelated folders.

The page also counts meaningful user records: journal entries, notes, To-Dos, projects, deadlines, upcoming events, media lists, exercise data, runs, and workout templates. It never displays file paths, user content, secrets, or environment values.

Backup storage distinguishes current ZIP packages from legacy database copies. Rolling ZIP packages retain the newest 10 validated packages; monthly ZIP archives retain the newest 12. Every rolling package created through the shared rolling helper is validated before retention runs. Legacy `.db` files remain visible separately and are outside modern ZIP retention. Migration and validation artifacts are excluded from the Usage count.

The Cloud section is a placeholder only: Supabase and Vercel are not connected and no provider requests are made. `UsageService.local_usage()` and `UsageService.database_counts()` keep the local summary separate so provider-specific adapters can be added after a future cloud migration.
