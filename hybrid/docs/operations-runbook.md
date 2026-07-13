# Operations runbook

## Start and health

The packaged InkOS process discovers a loopback port, generates a random bearer token, passes it only in the Runtime child environment, checks Runtime/schema versions and owns the PID file. Runtime refuses non-loopback `serve --host` values. Do not expose it by changing the host to `0.0.0.0`.

Use `story-runtime --db <db> compatibility`, then `serve`. `compatible` is runnable; `migration_required` requires the migration procedure; `schema_too_new` requires a newer app; other matrix states must be resolved before writes. Health must report `ok/ready` before Studio writes.

## Routine operations

- `checkpoint --mode PASSIVE` during normal service; use `TRUNCATE` only after observing WAL growth and quiescing heavy writes.
- `doctor <project> --deep` checks integrity and projection hashes.
- `snapshot <file.zip> --project-id <id>` performs SQLite online backup and checksums it.
- `diagnostics <project>` exports bounded redacted configuration, checks and recent errors.
- Rotate logs by size; retain five files by default. Never attach raw DB/chapter bodies to tickets unless explicitly approved.

## Incidents

- `DATABASE_LOCKED`: wait for the current writer; retry the same idempotency key. Windows antivirus/file locks should exclude the project directory only under organizational policy.
- Disk full/I/O/permission: stop writes, preserve DB/WAL/SHM together, free space or restore to a local writable disk, then run integrity check.
- Corruption: do not vacuum or mutate the only copy. Snapshot/copy the incident files, restore the newest verified snapshot into a new directory, run doctor/replay, then switch explicitly.
- Projection/outbox failure: authority may already be committed. Retry/rebuild only the disposable projection and compare projection hash.
- Runtime crash: process manager uses graceful termination and capped exponential restart. After restart, run health and doctor; retry response-loss commits with the same key.
- Network filesystem warning: move the database to a local disk. Network shares are unsupported.

## Vacuum and retention

Do not auto-VACUUM on every startup. Checkpoint first; run `VACUUM` only during planned downtime after a verified snapshot and enough free space. Snapshots, diagnostics and soak reports need an external retention policy; the Runtime does not delete user backups automatically.
