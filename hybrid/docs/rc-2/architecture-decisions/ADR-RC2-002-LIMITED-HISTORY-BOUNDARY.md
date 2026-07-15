# ADR-RC2-002: Limited History and Bootstrap Boundary

- Status: Accepted
- Decision: **APPROVED**
- Date: 2026-07-15

## Decision

Each project is classified as `native_complete`, `verified_import`, `bootstrap_boundary`, `manifest_only`, `pruned` or `unavailable`. Current-state-only projects use one explicit bootstrap manifest/event at R. Queries before R return `409 HISTORY_UNAVAILABLE`; they never return current, nearest, inferred or copied state.

Definitions:

- `history_available_from_revision`: earliest revision whose requested payload can be returned with authoritative semantics. Null means no state payload is available.
- `history_completeness`: the classification above, describing why and how history is available.
- `migration_boundary`: optional immutable reference containing boundary revision, kind, provenance ID and source checksum set.
- `history_pruned`: true only when a retention action intentionally removed payload after recording an immutable manifest/hash proof.
- `verified_import`: imported transitions whose original order, atomic boundaries, identities and hashes are independently evidenced and adapter-validated.
- `bootstrap_boundary`: one transition declaring that a complete current-state artifact set becomes Runtime authority at R without claims about R-1.

## Query and diff semantics

- A bootstrap legacy project has no queryable revision 0 unless verified evidence actually proves an empty revision 0.
- Metadata-only revision/provenance manifests may be visible before the payload boundary, but must carry `history_payload_availability=unavailable` and cannot satisfy `state(project,R)`.
- Unknown history is a first-class state represented by `unavailable`; it is not an empty state.
- Pre-boundary state/entity queries return `HISTORY_UNAVAILABLE` with the earliest available revision and boundary reason.
- Cross-boundary structural diff is rejected with `HISTORY_COMPARISON_UNAVAILABLE`. A separate metadata-only boundary response may say that bootstrap introduced an authority baseline, without claiming additions/changes relative to unknown state.
- A revision whose manifest remains but payload was deliberately removed returns `410 HISTORY_PRUNED`. Tombstone identity/provenance may remain policy-filtered; deleted prose is not retained merely to make history convenient.

Project status, every historical response, Studio banner, CLI error and TUI status expose the same availability contract. A project may remain limited forever.

## Later evidence

Finalized manifests are never rewritten. Later-discovered source material may be retained as provenance-only archival evidence, but it cannot retroactively become the existing project's authoritative pre-boundary history or splice into its hash chain. Promotion requires a separately approved migration into a new lineage/project identity with explicit mapping; the old bootstrap lineage remains intact.

## Bootstrap representation

The bootstrap event is a closed-catalog `project.bootstrap_boundary` transition referencing a content-addressed state manifest. It contains no fabricated per-row changes. Its manifest has `event_count=1`, `transition_kind=bootstrap`, boundary provenance and artifact hashes. It is the first finalized manifest in that managed lineage and may have `previous_revision=null` even when R is greater than zero.

## Rejected behavior

Copying current state to earlier revisions, importing one revision per row, using local Markdown to fill gaps, returning nearest state and rewriting the bootstrap manifest after cutover are prohibited.
