# RC-2B1D2 Ownership Matrix

| Field / payload | Authoritative owner | Reference holders | Forbidden duplicates | Verification |
|---|---|---|---|---|
| chapter body | `chapter_artifacts.body_text` | manifest artifact ref/hash, commit checksum | manifest/projection full body | schema, large CJK/binary fixture, tamper/delete |
| review body | `review_artifacts.artifact_json` | findings and review hashes | manifest full review | schema inspection and forbidden fields |
| domain event payload | `story_events.payload_json` | manifest ordered IDs/hashes/range/count | manifest payload | multi-event ordering/count/range tests |
| current story state | entity/fact/timeline/thread projections | manifest state hash only | manifest snapshot | forbidden-field and reconstruction tests |
| artifact hash | immutable artifact/commit checksum | manifest tagged hash | mutable projection authority | content recomputation and reference checks |
| event range | event sequence/ordinal | manifest acceleration fields | payload copy | ordering/range/count checks |
| command identity | idempotency/command ledger | manifest provenance | rebound identities | cross-table Doctor checks |
| commit identity | chapter commit | manifest/artifact/events | cross-project commit | reference and revision checks |
| revision | project pointer + one manifest transition | commit/event applied revision | artifact/event as revision authority | allocator/CAS and Doctor |
| manifest hash | immutable manifest | successor previous hash | artifact/event as chain authority | canonical/hash-chain tests |
| schema/version | owning record | Doctor supported-value policy | silent fallback | fail-closed compatibility tests |
| summaries/metadata | current projections/artifacts | IDs, counts and hashes | recoverable full state in manifest | schema and size tests |

## Gate 11 conclusion

YES. Thirteen dedicated tests prove that manifest size follows reference/event
membership rather than body size, cannot recover the body or full state, and does
not contain full event payload. Artifact deletion, content tamper, cross-project
reference and duplicate identity are detected/rejected. Event loss, order change,
range/command mismatch and compatibility defects are detected. Batch 1 still does
not claim complete event coverage.
