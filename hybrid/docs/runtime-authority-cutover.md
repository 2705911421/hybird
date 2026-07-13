# Runtime authority cutover

Only new projects may select `authorityMode: runtime`. InkOS creates the local
project metadata and creates the Runtime project through the HTTP API. Existing
projects remain `legacy`; Phase 4 performs no automatic data migration.

For Runtime authority, InkOS may generate prose and typed proposals, but the
only canonical mutation is `prepare -> validate -> commit` over HTTP. Chapter
Markdown, Truth files, JSON state, `memory.db`, indexes, exports, snapshots, FTS,
and vectors are non-authoritative and rebuildable. Direct Studio chapter/Truth
writes, Agent file tools, revision/resync/repair/import flows, control-file
writes, and chapter-index writes are rejected in code.

`shadow` remains a context read/comparison mode and is never a write authority.
InkOS does not open Runtime SQLite. Runtime does not invoke an LLM.

Before cutover, stop writers and take a database plus project-directory
snapshot. Runtime authority cannot be changed back in place. After any Runtime
chapter is finalized, rollback requires stopping writes, preserving commit
audit/event data, restoring the pre-cutover snapshot, and rolling back both
applications to compatible versions. Do not re-enable dual writes. Migration
3 may be rolled down only when no Runtime-authority commit must be retained; in
all other cases restore a complete v2 snapshot instead.
