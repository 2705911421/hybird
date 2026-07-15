# ADR-RC2-006: RC-2 Batch Order and Gates

- Status: Accepted
- Decision: **APPROVED**
- Date: 2026-07-15

## Mandatory order

| Batch | Entry gate | Exit gate |
| ---: | --- | --- |
| 1 Revision semantics | RC-2A.5 approved; manifest/ownership/boundary frozen | atomic allocator/manifest/CAS; continuity, idempotency and revision-neutral operations proven |
| 2 Event coverage | Batch 1 manifest available; catalog/envelope ADR accepted | 100% story-command coverage or explicit non-story classification; append-only and closed-catalog tests pass |
| 3 Historical storage/reducers | Batch 2 complete; reducer registry frozen | all required domains rebuild every available R; history intervals and snapshot/full replay hashes match |
| 4 Historical query service | Batch 3 parity; availability/error contracts frozen | one service resolves exact revisions, boundaries, auth and stable pagination; no current fallback |
| 5 Diff | Batch 4 stable state semantics | structural deterministic diff matches independent state comparison and reports source event IDs |
| 6 Replay jobs | Batch 3 reducer/snapshot stability and Batch 5 hashes | isolated verify/materialize and latest-only repair pass corruption/crash/quota tests |
| 7 Runtime API | Batches 4-6 internal contracts stable | strict Pydantic/OpenAPI behavior, limits, permissions and error taxonomy pass |
| 8 TypeScript client | Runtime API/OpenAPI frozen | Zod/contracts reject malformed/unknown versions; no SQLite/filesystem bypass |
| 9 Studio/CLI/TUI | client compatibility and Runtime semantics green | common revision/hash display, read-only historical mode and unavailable/pruned UX pass black-box tests |
| 10 Migration/compatibility | semantics, manifests, events, service and client frozen | every legacy project classified; bootstrap/verified import is idempotent and never fabricates history |
| 11 Performance | correctness suites green and representative corpus fixed | P50/P95/P99, plans, storage/RSS and quotas recorded without semantic shortcuts/SLO reduction |
| 12 CI gates | all prior exit evidence complete | clean default-branch cross-platform aggregate gate blocks release on any required failure |

## Serial and parallel work

The numbered semantic dependency is strict. Within a batch, independent documentation, fixtures, threat modeling and benchmarks may run in parallel after the entry gate. Schema/reducer/API/client/UI implementation cannot cross the next batch boundary. Batch 11 measurement harness design may be prepared earlier, but optimization decisions wait for correct semantics. Batch 12 workflow design may be drafted earlier, but cannot declare gates satisfied.

## Return-to-design conditions

Any need to fabricate pre-boundary state, weaken a closed event payload, allow domain-specific history semantics, mutate events during replay, overwrite latest with a target revision, accept an unavailable reducer, or bypass Runtime ownership returns the affected batch to RC-2A.5/ADR review. A failed hash/compatibility model, inability to make manifest finalization atomic or inability to define tombstone/retention semantics are also design failures, not test exceptions.

## Why UI/API/migration cannot move early

- UI would crystallize misleading semantics and create pressure for current fallback before Runtime truth exists.
- A public API before coverage would permanently expose domain-dependent pseudo-history and compatibility obligations.
- Migration before boundary/manifest semantics would either renumber, invent atomic transitions or make immutable records with the wrong meaning.

Authorization in this ADR is only for RC-2B Batch 1. Every later batch still requires its own entry evidence.
