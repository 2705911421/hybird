# RC-1 Gate Failure Baseline

Date: 2026-07-14 (Asia/Shanghai)

## Source Baseline

| Item | Value |
|---|---|
| branch | `master` |
| commit | `848cdd0d142067d01ec36f5bba0f85b59584e974` |
| upstream | `origin/master` contains the commit |
| git status | dirty: 52 entries (44 tracked modifications, 8 untracked entries) |
| Node / pnpm / Python | `v24.16.0` / `9.12.0` / `3.11.15` |
| OS | Windows 11 Home Chinese, 64-bit, `10.0.26200` |
| Runtime version | `0.1.0` |
| API contract version | `story-runtime/v1` |
| database schema version | `7` (`phase9_scale_indexes`) |
| project authority fixture | `book.authorityMode=runtime`; `storyRuntime.mode=story-runtime` |
| feature configuration observed | Runtime writes disabled by default (`STORY_RUNTIME_ENABLE_WRITES=0`); observability, recovery, and migration default enabled; unified review defaults enabled |
| current committed RC-1 CI | GitHub Actions run `29273890711`, `master@848cdd0`, success; old four-step Linux-only workflow |

## Dirty-Worktree Impact

The following uncommitted changes are in scope for the RC-1 result and can change the conclusion. This assessment is therefore of the **current working tree**, not a release candidate represented solely by commit `848cdd0`.

- Authority implementation: `inkos/packages/core/src/chapter-application-service.ts`, `pipeline/runner.ts`, `story-runtime/client.ts`, `story-runtime/context-provider.ts`, `agent/agent-tools.ts`, `agent/context-transform.ts`, `agents/composer.ts`, `agents/continuity.ts`, `utils/analytics.ts`, `utils/book-eval.ts`.
- Product surfaces: Studio `src/api/server.ts`, `src/pages/BookDetail.tsx`; CLI commands `analytics.ts`, `auto.ts`, `book.ts`, `config.ts`, `eval.ts`, `review.ts`, `status.ts`, `project-bootstrap.ts`; TUI `app.ts`, `dashboard.tsx`, `slash-autocomplete.ts`, plus untracked `tui/chapter-surface.ts`.
- Gate and CI: `.github/workflows/rc1-chapter-authority.yml`, `inkos/scripts/check-runtime-chapter-authority.mjs`.
- Test and fixture changes: Runtime `test_chapter_reads.py`; Core, CLI, Studio tests; `hybrid/fixtures/studio-phase6/inkos.json`; untracked TUI test.
- Documentation-only changes: the existing RC-1 architecture documents and five untracked RC-1 documents.

Unrelated-looking changes were not reverted or edited. The central impact is material: the new AST gate and expanded regression workflow are uncommitted, so neither is evidence that the committed RC has been protected in CI.

## CI Status Detail

`rc1-chapter-authority.yml` is committed and triggers on `push` and `pull_request`; its last default-branch run passed. At the baseline commit it runs only on Ubuntu and executes install, `check:chapter-authority`, Core typecheck, and one Core test file. The current dirty workflow adds fuller tests and Chromium, but remains Linux-only, is not in a completed CI run, and is not required by `.github/workflows/release.yml`.

No `continue-on-error` was found in the RC-1 workflow. Whether GitHub branch protection makes the job formally required/blocking cannot be determined from the repository.

## Commands Executed

All commands below completed successfully unless explicitly noted in the failure report.

- `python hybrid/scripts/check_architecture.py`
- `pnpm check:chapter-authority`
- `python -m pytest tests/unit/test_chapter_reads.py -q`
- targeted Core, CLI/TUI, and Studio regression commands from the current RC-1 workflow
- `python -m pytest -q`
- `pnpm typecheck`, `pnpm build`, and `pnpm test`
- `pnpm --filter @actalk/inkos-studio test:e2e -- --project=chromium`
- a fresh `%TEMP%/rc1-gate-*` Runtime/Studio/CLI six-case fixture matrix and seven Runtime-unavailable fault probes
