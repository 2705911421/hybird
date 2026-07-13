# Backup and restore

## Create and verify

Run `story-runtime --db project.db snapshot backups/project-YYYYMMDD.zip --project-id project-id`. The implementation uses SQLite online backup, integrity check and a ZIP with exactly `authority.db` and `manifest.json`. The manifest records SHA-256, byte size, app/Runtime/database/project schema, revision, logical projection hash, blob manifest and the index rebuild marker.

Store snapshots outside the project directory and test restore regularly. A successful command proves creation and checksum at that time; it does not prove off-site retention.

## Restore

Run `story-runtime restore snapshot.zip NEW_EMPTY_DIRECTORY`. Restore refuses a non-empty target, unexpected archive entries, checksum mismatch, integrity failure, logical projection hash mismatch and schema newer than the Runtime. For a compatible project snapshot it also returns a deep doctor report. It never overwrites the current project. After restore:

1. Review compatibility; migrate only after creating another snapshot if required.
2. Run deep doctor.
3. Verify/replay core projections and compare hashes.
4. Rebuild lexical/vector indexes when the manifest marker is true.
5. Open the restored project explicitly; keep the old directory until acceptance.

## Disaster drills

Automated coverage currently exercises online backup, checksum, new-directory restore, non-overwrite and zip-slip rejection. DB corruption, missing blob, unfinished outbox, projection corruption and Runtime restart have partial tests. Forced shutdown, ENOSPC, app/Runtime upgrade failure and full Windows file-lock drills require release-environment evidence and remain blockers.
