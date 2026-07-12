# Hybrid Story Runtime — Phase 1

This directory contains the independently runnable Python Story Runtime approved for Phase 1. It owns a local SQLite story database and exposes versioned read-only HTTP DTOs. It does not start InkOS, invoke an LLM, load Claude Code hooks, parse skill commands, or discover plugin installation directories.

## Phase 1 boundary

- Implemented: Pydantic contracts, SQLite repository layer, repeatable up/down migrations, deterministic fixture initialization, health/status/entity/context/RAG/doctor reads, recoverable lock/projection states, bearer protection, contract tests, and cross-platform launchers.
- Deliberately disabled: every approved HTTP write operation (`prepare`, `validate`, `commit`, `append`, `replay`, `migrate`, `export`). They validate their request DTO and return the contract-shaped `403 WRITE_FEATURE_DISABLED` response.
- Not implemented early: InkOS client integration, LLM calls, real project import, chapter authority cutover, asynchronous outbox consumers, or Studio UI.

Internal SQLite tables are private. Callers use only the DTOs defined in `../contracts/story-runtime.openapi.yaml` and `../contracts/schemas/`.

## Install and test

Python 3.11 or newer is required.

```text
cd hybrid/story-runtime
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
.venv\Scripts\python -m pytest
```

On macOS/Linux, activate with `. .venv/bin/activate` and use `python3` where required.

## Initialize the deterministic fixture

```text
story-runtime --db data/story.db migrate
story-runtime --db data/story.db init-fixture --fixture fixtures/lighthouse-project.json
story-runtime --db data/story.db init-fixture --fixture fixtures/lighthouse-project.json
story-runtime --db data/story.db status lighthouse-fixture
story-runtime --db data/story.db doctor lighthouse-fixture --deep
story-runtime --db data/story.db query lighthouse-fixture --entity char-lin --history
```

The second initialization returns `"replayed": true`; counts do not change. Fixture bootstrap is an explicit test/development CLI operation, not a public HTTP write path.

## Run the service

Set a local bearer token before shared-machine use. The default is intentionally obvious and suitable only for local development.

```text
set STORY_RUNTIME_TOKEN=a-local-secret
scripts\start-runtime.cmd
```

PowerShell can use `scripts/start-runtime.ps1`; macOS/Linux can use `scripts/start-runtime.sh` after `chmod +x scripts/start-runtime.sh`. The default endpoint is `http://127.0.0.1:47831/api/story-runtime/v1`.

```text
curl http://127.0.0.1:47831/api/story-runtime/v1/health
curl -H "Authorization: Bearer a-local-secret" http://127.0.0.1:47831/api/story-runtime/v1/projects/lighthouse-fixture/status
```

The CLI launchers require the package to be installed in the active Python environment. Configuration is local and explicit:

| Variable | Default | Purpose |
|---|---|---|
| `STORY_RUNTIME_DB` | `./data/story.db` | SQLite authority path |
| `STORY_RUNTIME_TOKEN` | `story-runtime-local` | Local HTTP bearer token |
| `STORY_RUNTIME_BUSY_TIMEOUT_MS` | `750` | SQLite lock wait |

`STORY_RUNTIME_ENABLE_WRITES` is reserved but ignored in Phase 1; no environment setting can enable unfinished write behavior.

## Query behavior

Exact entity lookup is authoritative. Context queries rank structured facts first and then add deterministic lexical retrieval candidates. Retrieval text is always labeled `untrusted_content`; it cannot override facts or become a command. The fixture demonstrates characters, relationships, events, timeline entries, narrative threads/foreshadowing, and chapter summaries.

## Recovery behavior

- A locked SQLite authority reports `health.status=degraded` and `database=locked`; the caller can retry after the active transaction ends.
- A failed projection is recorded as `retryable`. Status exposes a stable recovery hint without table names; doctor reports the replay action.
- Connections are always explicitly closed, including on Windows, so restarts and cleanup do not retain database handles.
- Migrations are checksummed and repeatable. Down migrations exist for smoke testing and development rollback; production recovery should use verified snapshots.

## Verification artifacts

- Tests: `tests/unit`, `tests/integration`, `tests/contract`, `tests/migration`.
- Fixture: `fixtures/lighthouse-project.json`.
- Provenance: `UPSTREAM_PROVENANCE.yml`.
- Known gaps: `KNOWN_DIFFERENCES.md`.
- Measured baseline: `BASELINE_PERFORMANCE.md`.

The upstream `inkos/` and `webnovel-writer/` trees are never imported or modified by this package.
