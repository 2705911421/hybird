# Hybrid Story System

This repository combines the InkOS TypeScript product shell with the Python
Story Runtime sidecar.

## Repository layout

- `inkos/`: InkOS CLI, TUI, Studio, agents, exports, and the Runtime client.
- `hybrid/story-runtime/`: independently runnable FastAPI and SQLite runtime.
- `hybrid/contracts/`: versioned OpenAPI and JSON Schema contracts.
- `hybrid/docs/`: architecture decisions, audit notes, and migration plans.

## Current boundary

Phase 8 is implemented. Story Runtime is the only long-form authority writer.
InkOS generates prose, typed proposals and review artifacts, and uses versioned
Runtime commands for context, validation, commit, review, replay and migration.
Legacy projects are read/export/migrate-only; Markdown and indexes are not authority.

See [`hybrid/README.md`](hybrid/README.md) for the design package and
[`hybrid/story-runtime/README.md`](hybrid/story-runtime/README.md) for runtime
installation, testing, and launch instructions.

## Verification

```text
cd hybrid/story-runtime
python -m pytest

cd ../..
python hybrid/scripts/check_architecture.py

cd inkos
pnpm install
pnpm build
pnpm test
```

The imported InkOS source remains AGPL-3.0-only. Upstream provenance and known
differences are recorded under `hybrid/story-runtime/`.
