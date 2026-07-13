# Studio Runtime observability

## Views

The Studio Runtime workbench is available at `#/runtime/overview` for Runtime-authority books. Each view has a stable hash route:

- `overview`: revision, chapter, phase, authority, prepare/blocked/recovery counts, projection/index health, versions, backup and last commit.
- `commits`: cursor-paginated history with chapter and state filters.
- `commits/{project}/{commit}`: transitions, checksums, events, projections, findings, human decision, error and repair guidance.
- `events`: cursor-paginated summary/evidence timeline. Full large payloads are not loaded.
- `projections`: checkpoint, revision, hash, retry count, last error and replay capability.
- `doctor`: read-only checks, recovery preview/confirmation, progress and audit trail.
- `reviews`: aggregate Runtime review state.
- `migration`: read-only schema state and confirmed resume when required.
- `configuration`: booleans/status only; no secret values.

## Runtime states

| State | Reads | Writes | Retry | Studio action |
| --- | --- | --- | --- | --- |
| `healthy` | available | available | yes | none |
| `degraded` | available | normally available | yes | inspect Doctor and retry disposable work |
| `unavailable` | unavailable | unavailable | yes | check local Runtime and retry |
| `version_mismatch` | blocked | blocked | no | update the older component |
| `migration_required` | may be blocked | blocked | after migration | preview and confirm migration resume |
| `database_locked` | cached reads may remain | blocked | yes | wait and retry |
| `recovery_required` | available | affected commit blocked | after recovery | follow Doctor preview |

Each state DTO includes what happened, read/write impact, retryability, user action, and disabled actions.

## Polling and performance

Overview uses 30-second polling. Active recovery history uses 3-second polling only while mounted. `document.visibilityState=hidden` pauses requests. Failures back off exponentially to five minutes. Runtime unavailable therefore cannot cause high-frequency requests or write locks. Deep doctor is user-triggered only.

All growing collections are paginated. Default/maximum limits are 25/100. Cursor errors require restarting from the first page. Event summary mode is the default; evidence is opt-in. Chapter prose is not part of observability DTOs.

## Accessibility

Tabs use `aria-current`, segmented event controls use `aria-pressed`, icon-only controls have labels, loading and error states are announced, tables remain keyboard navigable, and narrow layouts scroll tables/tabs without overlapping content.
