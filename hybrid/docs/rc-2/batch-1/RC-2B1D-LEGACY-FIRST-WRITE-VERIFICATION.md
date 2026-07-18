# RC-2B1D Legacy First-Write Verification

## Reusable migration-7 fixture

`tests/conftest.py::legacy_v7_database` builds a real schema-7 database with:

- project revision 7 and populated current entity/fact/chapter-summary state;
- no revision manifests;
- legacy events with `applied_revision=NULL`;
- one event with `schema_version=NULL`;
- one event with unknown `legacy-events/v999` compatibility;
- malformed optional legacy evidence metadata;
- a partial `PREPARED` chapter commit;
- Runtime authority enabled after the legacy cutover boundary.

The fixture records exact legacy rows before migration so every test can prove they remain byte-for-byte unchanged.

## Verified transitions

| Scenario | Result |
| --- | --- |
| schema 7 to migration 8 | additive; no manifests generated and legacy rows unchanged |
| first native typed diff | exactly boundary R7 plus native R8 |
| boundary provenance | `transition_kind=bootstrap`, `provenance_class=bootstrap_boundary`, no predecessor, zero events |
| native predecessor | R8 `previous_manifest_hash` equals boundary R7 hash |
| idempotent retry | returns R8 with replayed result; no R9 |
| ledger fault after allocator work | entire transaction rolls back: project stays R7, zero manifests, zero native events |
| retry after fault removal | creates only R7/R8 |
| concurrent first writes at expected R7 | one R8 success, one explicit `REVISION_CONFLICT`; no duplicate/gap |
| historical read below boundary | `at_revision=6` returns `HISTORY_NOT_IMPLEMENTED`, never current state |
| unknown old event schema | Doctor reports `UNKNOWN_EVENT_SCHEMA_VERSION`, marks replay unsafe, and does not rewrite the event |

No R0-R6 manifest is generated. Current entities/facts/summary and partial commit remain unchanged. NULL legacy event schema remains permitted, while an unknown non-NULL value is not silently treated as legacy.

## Scope statement

This verification establishes a current-state boundary and the safety of the first native write only. It does not make R0-R6 queryable, add history tables, reconstruct missing events, or change replay/`at_revision` behavior.
