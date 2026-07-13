# ADR-011: non-long-form data ownership after Runtime cutover

Status: accepted  
Date: 2026-07-13

## Decision

Story Runtime exclusively owns long-form story authority. Play, Short Fiction, Interactive Film and Translation are separate products, not compatibility paths for long-form authority.

| Capability | Owner and root | State | Long-form relationship |
|---|---|---|---|
| Play | InkOS `play/` stores | `play.db` plus run files | Independent simulation state; never imported as long-form canon automatically. |
| Short Fiction | InkOS `shorts/` | Standalone package files | Final short-form artifact; no Story Runtime project. |
| Interactive Film | InkOS `interactive-films/` | graph/authoring files and internal `memory.db` | Independent graph state. Its SQLite exception is isolated to Film tools and is not exported as a long-form API. |
| Translation | InkOS translation run/project roots | translation metadata and exports | Derived content; does not mutate source authority. |

Their tools may write only their own roots. The generic Studio artifact PUT allowlist contains only non-long-form generated roots. Long-form Agent sessions receive no generic file writer. Backups and exports follow each capability's own store; none can restore or modify a Runtime project.

FTS/vector/search indexes are rebuildable acceleration data and are never authority.

## Consequences

- Non-long-form SQLite is an explicit architecture-test exemption, not a hidden legacy fallback.
- Sharing DTO helpers does not transfer ownership.
- Converting a non-long-form artifact into a long-form project requires an explicit importer with provenance and user confirmation.
