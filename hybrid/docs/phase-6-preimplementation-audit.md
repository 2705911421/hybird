# Phase 6 preimplementation audit

Date: 2026-07-12

## Scope and authority boundary

Phase 6 adds a Studio observability and recovery surface for Story Runtime. Story Runtime remains the only authority for runtime state. Studio may call only `/api/story-runtime/v1` DTOs through its server-side proxy. It must not open the Runtime database, inspect `.story-system`, read the Runtime data directory, or reconstruct status from InkOS book files.

## Findings

1. **Studio routes and pages.** Studio is a React hash-routed application in `inkos/packages/studio/src`. `App.tsx` owns page composition, `use-hash-route.ts` owns route parsing, and `Sidebar.tsx` owns primary navigation. Existing pages use the shared Tailwind design tokens, Lucide icons, `useApi`, and narrow `max-w-*` layouts. The Runtime panel should extend this shell instead of importing the webnovel Dashboard UI.
2. **Current Runtime status API.** Runtime exposes unauthenticated health plus authenticated project status and doctor endpoints. Status currently reports revision, phase, latest chapter, authority mode, active prepare IDs, projection health, and schema version. It does not yet report blocked commits, recovery, backup, index, migration, configuration, or last successful commit.
3. **Public commit/event/projection DTOs.** Phase 4 has write DTOs and finalized commit results, but no public paginated commit list/detail DTO. Events have append/query-context shapes but no timeline list DTO. Projection replay has a write DTO and status is embedded as an untyped map; there is no public projection list DTO. New strict DTOs are required.
4. **Runtime fields that must remain internal.** SQL/table names, row IDs used only for storage, database filenames and absolute paths, raw `*_json` columns, request hashes, validation tokens, environment values, bearer/API/provider secrets, raw traceback text, full chapter bodies, and unbounded event payloads must not cross the observability API. Stable public IDs, checksums, revisions, status enums, timestamps, counts, redacted summaries, and explicit repair capabilities may cross it.
5. **webnovel Dashboard capabilities worth retaining.** Health and degraded-state distinctions, project phase, commit/projection progress, read-only doctor checks, RAG/index health, migration readiness, recent errors, recovery guidance, and bounded diagnostics are useful. These concepts should be served by Runtime DTOs and rendered in InkOS Studio.
6. **webnovel Dashboard capabilities to retire.** Direct scans of `.story-system/commits`, projection JSONL, index databases, generated files, and internal directories; SQL-derived UI assumptions; internal table terminology; absolute-path display; and command snippets requiring Claude Code or manual Python invocation are not carried forward.
7. **Studio authentication and local boundary.** Studio is a local Hono server and Runtime bearer configuration is resolved from `storyRuntime.apiTokenEnv`. Browser requests authenticate only to the local Studio origin. Runtime tokens are read by the Studio server process, forwarded in the `Authorization` header, and never returned to or stored by the browser. The Runtime health endpoint remains token-free; project data stays authenticated.
8. **Pagination.** Commits, events, recovery jobs, and other potentially growing collections require opaque cursor pagination with bounded limits. A cursor binds to project, collection, sort position, and filter fingerprint; changing filters or using a cursor from another collection/project returns a typed invalid-cursor error. Default page size is 25 and maximum is 100. Event payloads are summarized by default and expanded only per item/evidence request.
9. **Bearer token propagation.** `StoryRuntimeClient` owns Runtime requests. Studio constructs it per request from the freshly loaded project config and `process.env[apiTokenEnv]`. Browser DTOs contain only a boolean token-configuration status. Error objects, logs, diagnostic reports, and proxy response bodies are redacted before returning.
10. **Sensitive-data redaction.** Runtime applies a single recursive redactor to diagnostic/error/config surfaces. It masks API keys, bearer/Authorization values, provider secrets, database paths, home paths and usernames, and traceback path fragments. Chapter private content is omitted from observability DTOs. Studio applies a second defensive redaction and maps unexpected failures to stable user-facing error codes.
11. **Disconnected/degraded UX.** The UI maps Runtime state to `healthy`, `degraded`, `unavailable`, `version_mismatch`, `migration_required`, `database_locked`, or `recovery_required`. Each state declares read impact, write impact, retryability, recommended action, and disabled actions. Overview polling is low frequency, pauses when the document is hidden, backs off exponentially, and stops high-frequency requests while unavailable. Active jobs may poll faster.
12. **Recovery safety.** Refresh, read-only doctor, retrying an outbox item, rebuilding disposable lexical/vector indexes, and downloading a redacted diagnostic report are direct operations. Core projection replay, aborting a prepared commit, restoring a snapshot, clearing a retry queue, and resuming an interrupted migration require a preview plus explicit confirmation token. Deleting authoritative events/finalized commits, changing revisions/facts directly, arbitrary SQL, validation bypass, and forced revision overwrite are not exposed.

## Implementation decisions

- Add strict `observability/v1` DTOs and versioned endpoints inside Story Runtime.
- Keep list queries read-only and bounded; overview never runs deep doctor.
- Store recovery job state and audit entries in Runtime, not Studio.
- Represent unsupported or temporarily blocked recovery capabilities explicitly instead of exposing internal mechanisms.
- Keep CLI doctor/status behavior equivalent by using the same Runtime service layer.
- Gate Studio navigation and recovery execution separately so UI rollback cannot change Runtime authority or data.

## Test baseline and risks

The worktree contains active Phase 4/5 changes and untracked contracts/tests. Phase 6 must be additive and preserve those changes. Highest-risk areas are cursor validation, redaction of nested error data, recovery confirmation binding, malformed Runtime responses at the Studio proxy, and polling that could amplify lock contention. Deterministic SQLite fixtures and mocked Studio Runtime responses will cover those boundaries without an LLM.
