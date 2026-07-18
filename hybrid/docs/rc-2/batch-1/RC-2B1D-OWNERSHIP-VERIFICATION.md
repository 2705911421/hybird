# RC-2B1D Manifest / Event / Artifact Ownership Verification

## Authority split

| Component | Sole responsibility | Explicitly absent |
| --- | --- | --- |
| Manifest | proves one transition/revision and indexes hashes, counts, ranges, command/commit identity and artifact references | chapter/review body, complete story state, projections, full event payload |
| Event | expresses a domain mutation and its evidence/aggregate identity | proof that a project revision exists; large immutable chapter body |
| Artifact | preserves immutable chapter body, summary, review/proposal material and large payload | proof of project revision existence; domain mutation ledger |

The relationship remains:

```text
Manifest proves transition and integrity
Event expresses domain change
Artifact preserves immutable large content
```

No component can impersonate the other two as complete authority.

## Static guards

The architecture gate inspects the migration-8 manifest table definition. The RC-2B1D test also inspects SQLite `PRAGMA table_info(project_revisions)` and `RevisionManifest` dataclass fields. These guards reject manifest fields named `body`, `body_text`, `content`, `full_state`, `event_payload`, `payload_json`, `review_text`, `entities`, `facts`, `timeline`, `threads`, or `state_mutation_proposal_json`.

The allow-list remains identifiers, hashes, counts/ranges, transition/schema/provenance metadata, command/commit identity, state hash and artifact references. A size threshold is not used as a substitute for semantic field checks.

## Dynamic evidence

`tests/unit/test_rc2b1d_ownership.py` finalizes a real CJK chapter containing unique body and event-payload markers, then verifies:

- serialized manifest contains neither marker and cannot reconstruct the chapter or story state;
- artifact owns the exact chapter body and stored proposal/review material;
- event owns the domain mutation payload;
- manifest owns only the event membership/range/hash and chapter artifact reference/hash;
- deleting the artifact yields `manifest.artifact_hash.<revision>`;
- deleting an event yields `manifest.event_missing.<revision>`;
- unknown referenced artifact schema yields `UNKNOWN_ARTIFACT_SCHEMA_VERSION` and replay-unsafe status;
- commit revision tampering yields `COMMAND_COMMIT_MISMATCH`;
- event command rebinding yields `COMMAND_EVENT_RANGE_MISMATCH`.

Gate 11 is repeatable and passed. Batch 1 still uses the honest `legacy-unversioned` manifest event compatibility where appropriate and does not claim full event coverage.
