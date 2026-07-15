# Revision Manifest Implementation

## Authority responsibility

`project_revisions` is the sole proof that a revision exists. Each row identifies predecessor/hash, atomic command identity, optional chapter commit, idempotency/request hash, ordered event membership and hashes, artifact references and hashes, compatibility/provenance data, resulting state hash and accepted timestamp. It is an integrity and membership index.

It does not store chapter body text, summary bytes, complete event payloads, projections, snapshots, diffs or caches. Story events remain authority for concrete domain transitions; chapter artifacts remain authority for large chapter bytes. A manifest references and hashes those records but does not replace them.

## Schema and constraints

Migration 8 adds `project_revisions`, history-availability metadata and a manifest-writer handshake. The primary key is `(project_id, revision)`. Manifest ID and hash are globally unique. Project-scoped command and idempotency identities are unique; commit identity has a project-scoped partial unique index. Checks enforce non-negative revision, predecessor continuity or an explicit lineage start, and consistent event-count/range nullability.

SQLite triggers abort every update and delete with `project revision manifests are immutable`. The foreign key uses `ON DELETE RESTRICT`, so an ordinary project delete cannot cascade through the ledger. There is no normal application delete/update repository method. Retention/project deletion remains a separately governed forward transition/policy; Batch 1 does not implement it.

## Event and artifact membership

Ordered event IDs follow command ordinal order. Their logical envelope hashes cover the current legacy envelope except physical SQLite sequence. First/last sequence values are audit accelerators, not the definition of membership. Artifact pairs are deterministically sorted. Chapter finalize binds the immutable chapter artifact hash; bootstrap also binds all finalized chapter artifact hashes present at its boundary.

The doctor recalculates manifest hash, previous hash, ordered membership hash, event hashes/ranges/revisions, artifact hashes, committed command/finalized chapter transition linkage, compatibility values and latest-pointer consistency. It diagnoses only and never creates missing history.
