# Compatibility and Failure Policy

Status: **Frozen / Accepted 2026-07-15**

## Default rule

Authority writes and historical reconstruction fail closed. No unknown input is ignored, mapped to a default aggregate, read from current as fallback or “repaired” by deleting authority. Latest reads may continue only when the table below explicitly permits a previously verified current projection and the fault cannot affect its state; status must be degraded and writes remain blocked where specified.

Abbreviations: **W** blocks project story writes; **L** permits latest read; **H** permits historical read. “No” means the affected path fails before returning state.

| Condition / error code | HTTP | Retryable | Operator / repair action | W | L | H | Migration |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- |
| unknown event type `EVENT_TYPE_UNKNOWN` | 409 | no | install signed catalog/adapter or quarantine source and bootstrap; never skip | yes | only if event is provably outside current lineage; otherwise no | no for affected range | adapter or bootstrap |
| unknown aggregate `AGGREGATE_TYPE_UNKNOWN` | 409 | no | install matching catalog/reducer; never default to fact | yes | no | no | adapter/bootstrap |
| unknown event schema `EVENT_SCHEMA_INCOMPATIBLE` | 409 | no | install compatible reader/adapter or restore matching Runtime | yes | only with verified unaffected latest hash | no for affected range | often |
| unknown payload schema `PAYLOAD_SCHEMA_INCOMPATIBLE` | 409 | no | install deterministic payload adapter with fixture/hash proof | yes | only with verified unaffected latest hash | no | often |
| unknown reducer family `REDUCER_FAMILY_UNKNOWN` | 409 | no | install registered reducer family; audit catalog | yes | no | no | adapter/bootstrap if legacy |
| reducer version unavailable `REDUCER_VERSION_INCOMPATIBLE` | 409 | no | restore/install exact reducer or approved deterministic compatibility adapter | yes | current projection may be read only if its manifest/hash was already verified and no repair is needed | no | compatibility migration may be required |
| invalid ordinal `EVENT_ORDINAL_INVALID` | 409 | no | quarantine stream, compare manifest order/source backup; do not reorder finalized events | yes | no unless fault is wholly after latest (normally impossible) | no | source correction before import only |
| duplicate event ID with different hash `EVENT_ID_COLLISION` | 409 | no | security/corruption investigation; restore authority backup | yes | no | no | no automatic migration |
| exact duplicate event ID/hash `EVENT_DUPLICATE_EXACT` | 200 existing result on command; 409 during raw audit | no | treat command retry through idempotency ledger; raw duplicate row is schema violation | no for valid retry; yes for stored duplicate | yes for valid retry | no until stored duplication resolved | schema cleanup before cutover |
| logical duplicate `LOGICAL_EVENT_DUPLICATE` | 409 or existing idempotent result | no | resolve command/idempotency identity; never apply twice | yes on conflict | existing verified latest only | no affected range | possibly adapter dedupe with proof |
| missing manifest `REVISION_MANIFEST_MISSING` | 409 | no | rebuild only from authoritative backup; do not infer from events/current | yes | latest only if requested/current manifest is intact; otherwise no | no | bootstrap only for legacy current state |
| event range mismatch `MANIFEST_EVENT_RANGE_MISMATCH` | 409 | no | verify ordered IDs/hashes against backup; restore missing authority | yes | no for affected/current lineage | no | source re-import before cutover only |
| manifest/event/state hash mismatch `AUTHORITY_HASH_MISMATCH` | 409 | no | isolate project, compare immutable backup, run verify; repair derived tables only after authority is established | yes | no | no | no automatic migration |
| missing required artifact `ARTIFACT_MISSING` | 409 | maybe if storage transient | restore hash-matching artifact from backup/object store | yes when command/current depends on it | metadata-only only; no body/derived state | no affected payload | import source only with exact hash proof |
| snapshot mismatch `SNAPSHOT_INCOMPATIBLE` | internal fallback; 409 only if no replay base | yes when earlier base exists | discard snapshot, try earlier compatible snapshot, then full replay | no unless no reconstructible base for write validation | verified current latest yes | yes if fallback succeeds; otherwise no | none |
| missing revision `REVISION_NOT_FOUND` | 404 | no | inspect manifest list; no repair from arithmetic range | no | yes | no for requested R | none |
| pre-boundary history `HISTORY_UNAVAILABLE` | 409 | no | display boundary/provenance; do not infer | no | yes | no before boundary | optional new lineage only |
| retention-pruned payload `HISTORY_PRUNED` | 410 | no | show retention proof; restore only if policy and exact hash authorize | policy-dependent | yes if latest retained | metadata/tombstone only as declared | none |

## Project state transitions

Compatibility faults create an immutable incident linked to project, manifest/event range, installed versions and redacted diagnostics. A write block is cleared only by a verified operator action that does not mutate finalized authority. Read permissions in the table are evaluated per affected revision/domain; a mixed-domain historical 200 is prohibited.

## Repair hierarchy

1. Re-read/reauthorize transient storage.
2. Reject a bad snapshot and replay from earlier verified base.
3. Rebuild derived current/history/index data from intact authority and compare hashes.
4. Restore missing immutable authority from a hash-matching backup.
5. For legacy pre-cutover input, apply a versioned adapter or choose an honest bootstrap boundary.
6. If authority remains ambiguous, keep the project blocked/unavailable. Do not delete, reorder, rewrite or synthesize events/manifests.
