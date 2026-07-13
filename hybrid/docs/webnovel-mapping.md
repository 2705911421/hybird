# webnovel-writer Phase 7 mapping

The adapter recognizes `.webnovel/state.json`, commit/event JSON, contracts, chapters, volumes, reviews, project memory, `index.db`, and `vectors.db`.

- Commit and event JSON map to CIR events with original IDs and payload provenance.
- Chapters map by number plus body checksum; volumes remain documents/extensions until a native volume projection exists.
- Reviews retain their original body hash and block on mismatch.
- `index.db` is opened with SQLite `mode=ro&immutable=1` and integrity checked. It is evidence/mirror input, not an assumed winner.
- `vectors.db` embeddings are not migrated. Only rebuildable document and metadata descriptions enter CIR.
- Project memory is untrusted/candidate evidence and cannot replace higher-confidence chapter or commit evidence.

When JSON and SQLite counts or values differ, the mapper compares available event IDs, commit/checksum fields and projection metadata, then emits a blocking conflict. The operator may choose a candidate, merge with an auditable rule, ignore, or quarantine. “SQLite wins” and “latest file wins” are prohibited defaults.

