# RC-2B1D Defect Fix Report

## Outcome

RC-2B1D closes the independently confirmed Batch 1 Doctor and architecture-enforcement defects and converts Gate 11 and Gate 15 from verification gaps into repeatable automated evidence. The repair remains within Batch 1 and is ready for a separate independent regate after push. This task does not push or start that regate.

Base candidate: `790e06d231daa33ce3774cc065e21c059d7680d7`.

## Fixed defects

1. Added a single compatibility registry and fail-closed Doctor diagnostics for unknown manifest/event/reducer/artifact/hash/canonicalization/provenance/contract/transition values.
2. Added structured Doctor evidence: project/revision/field/observed/supported/severity/verification-stop/replay-safety.
3. Added provenance consistency across deterministic command identity, project-scoped ledger, finalized commit, artifact references and event command range. Recomputed manifest self-hashes no longer hide `command_id` tampering.
4. Added explicit chain-health propagation and impact summary from the first untrusted revision through all descendants.
5. Replaced the `migration_jobs.py` file exemption with a complete production scan closure and exact symbol-level exceptions.
6. Added repeatable Gate 11 ownership and schema guards.
7. Added a reusable schema-7 legacy fixture and Gate 15 first-write, rollback/retry and concurrency tests.
8. Updated the approved OpenAPI Doctor contract for the new optional evidence fields.

## Core semantics unchanged

Revision 0 creation, unified CAS allocation, one authority transition per revision, immutable manifest triggers, canonical predecessor chain, honest bootstrap boundary, retry idempotency, revision-neutral failures/conflicts, chapter finalize and typed diff production paths were not redesigned. Migration 8 remains the latest schema migration; no old event is rewritten.

## Completion gates

| # | Gate | Result |
| --- | --- | --- |
| 1 | Doctor detects unknown manifest schema | YES |
| 2 | Doctor detects unknown event schema | YES |
| 3 | Doctor detects unknown reducer/compatibility | YES |
| 4 | Doctor detects command missing/rebound/mismatch | YES |
| 5 | recomputed self-hash cannot hide provenance tamper | YES |
| 6 | first chain corruption identified | YES |
| 7 | all downstream revisions marked affected | YES |
| 8 | all production Python files scanned by default | YES |
| 9 | `migration_jobs.py` blind spot removed | YES |
| 10 | new production files enter scan automatically | YES |
| 11 | helper/indirect bypass detected at defining symbol | YES |
| 12 | architecture mutation matrix effective | YES |
| 13 | manifest/event/artifact split automated | YES |
| 14 | manifest contains no full body/event payload | YES |
| 15 | legacy first-write matrix complete | YES |
| 16 | no fabricated R0-R6 | YES |
| 17 | first native write creates correct next revision | YES |
| 18 | retry/concurrency has no duplicate/gap | YES |
| 19 | Batch 2 not started | YES |
| 20 | relevant Runtime/InkOS regressions pass | YES |
| 21 | repository has no Gate DB/log/coverage/report residue | YES |
| 22 | documentation and implementation agree | YES |

## Explicit non-goals

RC-2B1D does not implement a closed typed event catalog, complete mutation-event coverage, history tables, `HistoricalStateService`, public historical state queries, real `at_revision`, target-revision replay, a TypeScript historical client, or Studio/CLI/TUI time travel. `HISTORY_NOT_IMPLEMENTED` remains the approved fail-closed response.

## Release Readiness

Phase 9 Windows InkOS, `pip-audit`, and deterministic Studio clean-build failures remain Batch 12 issues. No Phase 9 workflow or unrelated dependency/build code changed. A dedicated RC-2 aggregate workflow still does not exist and must not be implied by this repair.

## Verdict

```text
RC-2B1D DEFECT FIX COMPLETE
READY FOR INDEPENDENT REGATE
```
