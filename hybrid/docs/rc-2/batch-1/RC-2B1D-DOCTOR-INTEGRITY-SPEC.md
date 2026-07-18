# RC-2B1D Doctor Integrity Specification

## Purpose and boundary

Doctor verifies whether an existing Batch 1 revision-manifest lineage can be trusted. It never repairs, rewrites, synthesizes, replays, or backfills history. Unknown compatibility is fail-closed. This specification adds no historical query capability and does not claim complete event coverage.

## Central compatibility registry

All supported values and their diagnostics are defined once in `story_runtime/revision_compatibility.py`. Doctor consumes that registry; compatibility literals are not scattered through Doctor control flow.

| Logical field | Supported Batch 1 values | Diagnostic | Integrity action |
| --- | --- | --- | --- |
| `manifest_schema_version` | `revision-manifest/v1` | `UNKNOWN_MANIFEST_SCHEMA_VERSION` | stop canonical/self-hash verification from that revision |
| `event_schema_version` | `legacy-unversioned`, `story-runtime/v1` | `UNKNOWN_EVENT_SCHEMA_VERSION` | mark replay unsafe; NULL legacy rows remain allowed |
| `reducer_version` | `story-reducers/legacy-v1`, `story-reducers/not-applicable` | `UNKNOWN_REDUCER_VERSION` | mark replay unsafe |
| referenced artifact schema | `story-runtime/v1`, `review-artifacts/v1` | `UNKNOWN_ARTIFACT_SCHEMA_VERSION` | mark artifact interpretation/replay unsafe |
| hash tag | `sha256` | `UNKNOWN_HASH_ALGORITHM` | stop hash verification at that revision |
| canonicalization | `manifest-canonical-json/v1` | `UNKNOWN_CANONICALIZATION_VERSION` | stop canonical hash verification |
| provenance class | `native`, `verified_import`, `bootstrap_boundary`, `compensation` | `UNKNOWN_PROVENANCE_VERSION` | mark provenance/replay unsafe |
| transition kind | migration-8 transition allow-list | `UNKNOWN_COMPATIBILITY_VERSION` | mark transition interpretation unsafe |
| Runtime contract | `story-runtime/v1` | `UNKNOWN_COMPATIBILITY_VERSION` | mark compatibility/replay unsafe |
| bootstrap compatibility | `bootstrap-boundary/v1` logical policy | `UNKNOWN_COMPATIBILITY_VERSION` | derived from existing bootstrap fields; no new column |

Hash algorithm and canonicalization version are verification policy derived from existing tagged hashes and manifest schema. Migration 8 has no separate columns for them. RC-2B1D deliberately does not add a migration merely to duplicate derivable policy.

## Structured Doctor output

`DoctorCheck` retains its original fields and adds optional structured evidence:

- `project_id`, `revision`, `field`, `observed_value`, `supported_values`;
- `severity`, `verification_stopped`, `replay_safe`;
- `chain_health`, `chain_impact_start`, `chain_impact_end`;
- `latest_trusted_revision`, `first_untrusted_revision`, `total_affected_revisions`.

The approved OpenAPI schema permits these fields. Unknown values produce `fail` checks and make the overall Doctor status `blocked`; Doctor never emits `manifest.chain=pass` when any integrity issue exists.

## Command provenance over the real schema

There is no command table and no `chapter_commits.command_id` column in migration 8. Doctor therefore validates only relationships that really exist:

1. `project.create` command identity is deterministically derived from `project_id` and checked against its project-scoped idempotency ledger row.
2. `domain_command` identity is deterministically derived from `project_id + idempotency_key`; ledger operation, request hash, resulting revision and event `commit_id`/provenance identity are cross-checked.
3. `chapter_finalize` / `chapter_replace` identity is `chapter.finalize:<commit_id>`; manifest project/revision/idempotency/commit reference are checked against the finalized commit, lifecycle ledger result, artifact reference and event `commit_id`.
4. Bootstrap identity is `history.bootstrap:<project_id>` and intentionally has no idempotency-ledger command row.

Implemented provenance diagnostics include:

- `MANIFEST_COMMAND_REFERENCE_MISSING`;
- `MANIFEST_COMMAND_REFERENCE_MISMATCH`;
- `COMMAND_REVISION_MISMATCH`;
- `COMMAND_PROJECT_MISMATCH`;
- `COMMAND_COMMIT_MISMATCH`;
- `COMMAND_EVENT_RANGE_MISMATCH`;
- `DUPLICATE_COMMAND_ID`;
- `COMMAND_ID_REBOUND`;
- `COMMAND_PROVENANCE_INCOMPLETE`.

Because these are cross-table checks, changing `manifest.command_id` and recomputing `manifest_hash` does not evade Doctor.

## Chain-health state model

| State | Meaning |
| --- | --- |
| `VALID` | no direct or inherited integrity defect |
| `CORRUPTED` | this revision has a direct hash/reference/provenance defect |
| `AFFECTED_BY_PRIOR_CORRUPTION` | local fields may match, but the trust root is already broken |
| `UNVERIFIABLE_UNKNOWN_VERSION` | schema/hash/canonicalization is unknown, so trustworthy verification cannot continue |
| `MISSING_PREDECESSOR` | predecessor row is missing or lineage is non-contiguous |

Doctor finds the first untrusted revision, reports each direct defect once, marks all later non-direct revisions as affected, and emits one `MANIFEST_CHAIN_IMPACT` summary. A later revision with its own defect remains `CORRUPTED`; it is not reduced to an inherited-only issue.

## Repair policy

All integrity failures recommend restoring exact immutable authority from a verified whole-database backup. Doctor does not:

- recompute stored hashes;
- rewrite compatibility values;
- generate missing intermediate manifests;
- copy current state into historical revisions;
- delete or rewrite events/artifacts;
- open historical replay or query behavior.
