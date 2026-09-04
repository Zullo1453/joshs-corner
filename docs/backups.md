# Backups and retention

Josh's Corner stores current backup packages as validated ZIP files. A package contains a SQLite copy, attachments, a manifest, and SHA-256 checksums.

- Rolling ZIP packages retain the newest **10** validated packages.
- Monthly ZIP archives retain the newest **12** validated archives.
- Retention runs only after a newly created package validates successfully. Invalid packages never cause older valid packages to be removed.
- `create_rolling_backup_package()` is the shared create → validate → retain path for rolling packages, including release-audit helpers and scheduled backups.

Historical `.db` backup files are legacy backups. They are deliberately outside ZIP retention and are reported separately in Intelligence → Usage. Migration and validation artifacts are also outside the current retention and Usage package counts.
