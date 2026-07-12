# Hybrid Story System

This repository combines the InkOS TypeScript product shell with the Python
Story Runtime sidecar.

## Repository layout

- `inkos/`: InkOS CLI, Studio, agents, and the Phase 2/3 Story Runtime client.
- `hybrid/story-runtime/`: independently runnable FastAPI and SQLite runtime.
- `hybrid/contracts/`: versioned OpenAPI and JSON Schema contracts.
- `hybrid/docs/`: architecture decisions, audit notes, and migration plans.

## Current boundary

The integration is at Phase 2/3. InkOS can query Story Runtime for governed
context in legacy, shadow, or story-runtime mode. InkOS remains responsible for
chapter persistence, and Story Runtime HTTP write endpoints remain disabled.

See [`hybrid/README.md`](hybrid/README.md) for the design package and
[`hybrid/story-runtime/README.md`](hybrid/story-runtime/README.md) for runtime
installation, testing, and launch instructions.

## Verification

```text
cd hybrid/story-runtime
python -m pytest

cd ../../inkos
pnpm install
pnpm build
pnpm test
```

The imported InkOS source remains AGPL-3.0-only. Upstream provenance and known
differences are recorded under `hybrid/story-runtime/`.
