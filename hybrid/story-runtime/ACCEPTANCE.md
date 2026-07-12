# Phase 1 acceptance evidence

Verified on 2026-07-12 (Asia/Shanghai), Windows 11, Python 3.11.15.

## Automated gates

| Gate | Evidence | Result |
|---|---|---|
| Runtime unit/integration/contract/migration suite | `python -m pytest -q` | 21 passed |
| Editable package installation | `python -m pip install -e ".[test]"` | passed |
| Dependency consistency | `python -m pip check` | no broken requirements |
| Python compilation | `python -m compileall -q src tests scripts` | passed |
| Real process startup | module CLI on `127.0.0.1:47839`, HTTP health/status | `ok`, DB `ready`, revision 7 |
| Upstream focused regression | 10 relevant webnovel-writer test files with `--no-cov` | 77 passed |
| Upstream mutation check | nested `git status --short` for InkOS and webnovel-writer | both clean |

The known full upstream baseline failures are recorded in `../docs/baseline-tests.md`; Phase 1 neither changes nor masks them.

## Acceptance mapping

| Requirement | Proof |
|---|---|
| New fixture project initializes | CLI and `test_cli_initializes_and_reads_fixture` initialize `lighthouse-fixture` from an empty migrated DB. |
| Read characters, relationships, events, timeline, foreshadowing, summaries | Fixture count/idempotency test checks all six stores; authoritative-fact contract test checks all six public predicates. |
| Exact query | Entity service/API/CLI return `char-lin` and its revisioned history. |
| RAG query | Deterministic context and repository tests return ranked candidates labeled `untrusted_content`. |
| Repeated request creates no duplicate | Repeating fixture initialization with the same idempotency key returns `replayed=true`; counts remain fixed. |
| State survives restart | A new Database/Repository/Service object reads revision 7 and the missing character state from the same file. |
| SQLite lock is recoverable | Exclusive-lock integration test reports HTTP health semantics `degraded/locked`, then returns to `ready`. |
| Projection failure is recoverable | Injected projection failure produces `degraded`, `recoverable=true`, and doctor repair `replay projection`. |
| No Claude Code required | Static boundary test rejects Claude env/plugin references; package install and process smoke run without Claude. |
| No InkOS process required | The package imports neither InkOS nor its project tree; all tests and the real process smoke run standalone. |
| Original tests not harmed | No upstream files changed; 77 relevant upstream tests pass unchanged. |
| Writes remain closed | All seven approved write DTOs validate, then return contract-shaped `403 WRITE_FEATURE_DISABLED`. |
| API does not expose SQLite schema | Contract test scans generated OpenAPI for private table names and validates approved read DTOs. |

## Doctor output for the healthy fixture

```json
{
  "project_id": "lighthouse-fixture",
  "revision": 7,
  "status": "ok",
  "checks": [
    {"code": "schema.current", "status": "pass", "message": "schema migration 2 is current", "repair": null},
    {"code": "authority.integrity", "status": "pass", "message": "SQLite integrity check passed", "repair": null},
    {"code": "writes.feature_flag", "status": "pass", "message": "HTTP write endpoints are disabled for Phase 1", "repair": null},
    {"code": "projections.core", "status": "pass", "message": "all core projections are ready", "repair": null}
  ]
}
```

## Scope assertion

No InkOS source, webnovel-writer source, Claude hook, plugin directory, real LLM integration, Studio adapter, chapter write coordinator, or later migration phase is included in this change.
