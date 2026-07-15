# ADR-RC2-005: Replay, Verification and Latest Repair Boundary

- Status: Accepted
- Decision: **APPROVED WITH CONDITIONS**
- Date: 2026-07-15

## Three distinct operations

### Historical materialization

Reconstructs an available target revision R into an isolated temporary read model. It never changes events, manifests, project revision, current projections or latest checkpoints. It may run synchronously only inside bounded cost limits; otherwise it is an asynchronous job.

### Verify

Reconstructs in isolation and compares manifest/snapshot/event/state hashes. It persists an auditable job result but never mutates latest. Hash mismatch is a successful diagnostic outcome (`MISMATCH`), not permission to repair.

### Repair latest

Requires `projection:repair`, target equal to latest at both job start and atomic swap, a complete compatible event range/base snapshot, expected hash and result hash match. It rebuilds outside current tables, verifies all projections, then atomically swaps the selected latest projection set and checkpoints. Events, manifests and project revision remain unchanged. If latest advances, the swap aborts as stale.

## Job contract

Every job records:

- `job_id`, project, actor/authorization scope and idempotency key;
- mode `materialize|verify|repair`, `dry_run`, target revision and resolved latest revision;
- selected versioned projection set;
- inclusive event sequence/revision range and ordinal checks;
- snapshot base ID/revision/offset/checksum;
- event, payload, schema and reducer versions;
- expected/result manifest and state hashes;
- status, progress, bounded diagnostics, cost accounting and whether a latest swap occurred.

Statuses are `QUEUED`, `RUNNING`, `CANCELLING`, `SUCCEEDED`, `MISMATCH`, `FAILED`, `CANCELLED`, `STALE`. Terminal records are immutable except retention redaction fields that preserve hashes.

## Safety and operations

- Cancellation is safe before atomic latest swap. During the short swap critical section it is rejected/deferred; after swap, cancellation cannot relabel success.
- Concurrency is bounded per project and caller. One repair job per project; verify/materialize jobs use configured CPU, memory, event-count, revision-span, wall-time and temporary-storage quotas.
- Crash recovery resumes from a verified immutable snapshot/checkpoint or restarts the isolated build. A partially built namespace is never served or swapped.
- A partial event range requires an exact compatible base snapshot/materialization. Without one, the job fails before clearing or applying anything.
- Unknown type/version, invalid ordinal, missing manifest/artifact or hash mismatch fails closed and identifies operator action.

## Prohibitions

Replay to R2 cannot leave latest tables at R2; target materialization cannot write a current-revision checkpoint; replay cannot delete or rewrite events; and no job may silently skip incompatible inputs. Replay job sequence/state is operational audit, never a project story revision.

## Approval conditions

Batch 6 implementation must be preceded by accepted versioned reducers and isolated historical storage, and must pass crash/cancellation/concurrency/hash tests before repair permission is enabled.
