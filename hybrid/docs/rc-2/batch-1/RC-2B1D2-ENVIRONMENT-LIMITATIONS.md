# RC-2B1D2 Environment Limitations

## Local InkOS

- Node: 24.16.0
- pnpm: 11.13.0
- Declared engine: pnpm >=9; no exact repository pin
- Command: `pnpm.cmd --filter @actalk/inkos-core test`
- Result: NOT VERIFIED — ENVIRONMENT LIMITATION
- Error: dependency validation/install stopped with `ERR_PNPM_IGNORED_BUILDS`;
  pnpm also warned that `package.json` `pnpm.overrides` is no longer read.
- Direct `pnpm ... exec vitest run` retried dependency validation and stopped with
  `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`.

No pnpm version, dependency, lockfile, workspace configuration or build approval
was changed. Generated lock/workspace diffs and `.pnpm-store` were removed. Core,
Studio, CLI/TUI, Chromium E2E, typecheck and build are therefore not reported as
passing locally. This has no causal connection to the Runtime-only RC-2B1D2 diff.

## CI and release readiness

The prior same-SHA RC-1 first-attempt timeout followed by a successful rerun remains
transient CI instability. Existing Phase 9 failures remain a release-readiness
issue. RC-2B1D2 does not modify those workflows and does not claim repository-wide
green CI. A new same-SHA CI record cannot exist before the explicitly separate push.
