# ADR-RC2-003: Hybrid Historical Architecture

- Status: Accepted
- Decision: **APPROVED WITH CONDITIONS — Option C**
- Date: 2026-07-15

## Chosen architecture

The Runtime adopts the Hybrid model:

- immutable revision manifests define revision existence, order and integrity;
- the append-only typed event stream is authority for domain transitions;
- immutable content-addressed chapter/bootstrap artifacts are authority for large referenced payloads;
- current projections serve latest reads;
- validity-interval history tables serve routine historical reads;
- versioned snapshots plus replay independently verify, recover and materialize long ranges;
- historical materialization is isolated from latest projections.

Option A is rejected because validity rows cannot recover unsupported direct writes and provide no independent reconstruction proof. Option B is rejected as the sole read path because incomplete legacy events and unbounded replay costs make it unsafe today. Option C preserves bounded SQLite reads while retaining event-based verification and recovery.

## Frozen ownership and access rules

1. No datum has two authorities. Manifests own revision membership/integrity; events own domain transition semantics; artifacts own referenced chapter/bootstrap bytes. Current/history tables and snapshots are derived.
2. Current projections are writable only by the same deterministic reducer transaction that appends/finalizes authority, or by authorized latest-only repair.
3. History-table interval closure/insertion occurs in the authority transaction before manifest finalization. No asynchronous history writer can satisfy formal `at_revision` semantics.
4. `HistoricalStateService` is the only Runtime application entry for historical state. Routes, replay jobs and clients cannot compose their own historical SQL/replay.
5. Latest reads normally use current projections, resolving latest once. Historical reads never use current projections, including when R happens to equal latest; an explicit optimized path is allowed only if it verifies the projection against the same manifest and exposes identical semantics.
6. Diff uses revision manifests/change indexes to locate candidates, then history rows or isolated materialization to produce a structural, hash-verified result. A textual JSON diff is insufficient.
7. Snapshots are non-authoritative accelerators. A checksum/version mismatch discards the snapshot, falls back to an earlier compatible snapshot and replays events.
8. If a history table is lost or corrupt, rebuild it in isolation from a compatible snapshot plus authoritative events, verify its state hash, then atomically swap only that derived history model.

## Replay boundary

Target-revision replay never overwrites latest projection tables or latest checkpoints. Historical materialization writes an isolated temporary/read-model namespace. Only `repair latest`, with target equal to the resolved latest manifest, explicit permission and verified expected hash, may atomically replace current projections.

## Approval conditions

- Batch 1 must establish manifest/CAS atomicity.
- Batch 2 must close event coverage and append-only enforcement before historical APIs.
- Batch 3 must prove snapshot/full replay parity and history-table rebuildability.
- Runtime remains the sole SQLite owner; TypeScript and UI use the HTTP contract only.
