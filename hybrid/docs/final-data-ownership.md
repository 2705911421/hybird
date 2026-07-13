# Final data ownership

Date: 2026-07-13

| Data | Sole owner | Other components |
|---|---|---|
| long-form chapters and revision | Story Runtime | InkOS generates proposal/body and requests commit |
| facts, entities, relationships, timeline, narrative threads | Story Runtime | Studio sends typed diffs; no file/DB edits |
| event log and commit state | Story Runtime | read-only API consumers |
| core projections and status | Story Runtime | Studio is the single product panel |
| review artifacts and human decisions | Story Runtime | InkOS maps/displays typed artifacts |
| migration decisions, provenance and snapshots | Story Runtime migration service | Studio operates the versioned workflow |
| Markdown/TXT/EPUB/readable snapshots | projection/export pipeline | non-authoritative and rebuildable |
| FTS/vector/search indexes | Runtime outbox/index workers | rebuildable; never authority |
| InkOS project/provider/session settings | InkOS | not story canon |
| Play/Short/Film/Translation state | InkOS feature-specific owner | independent per ADR-011 |

InkOS and Studio never open Runtime SQLite or its data directory. TypeScript consumes versioned HTTP contracts. Runtime never calls an LLM.
