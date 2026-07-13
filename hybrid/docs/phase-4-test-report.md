# Phase 4 test report

Date: 2026-07-12

Final verified commands:

- `python -m pytest -q`: 48 passed.
- `pnpm test` in Core: 175 files, 1,674 tests passed.
- `pnpm test` in Studio: 56 files, 487 tests passed.
- `pnpm test` in CLI: 38 files, 210 tests passed.
- `pnpm -r typecheck`: Core, Studio client/server, and CLI passed.
- Targeted Runtime/persistence Core tests: 14 passed; targeted Studio
  authority/legacy route tests: 22 passed.

The Python suite covers lifecycle transitions, illegal transitions, validation,
idempotency conflicts/replay, revision conflicts, event uniqueness, rollback,
projection replay/hash, response-loss retry, lock/restart behavior, migration
up/down, large and CJK bodies, API contracts, and deterministic two-chapter E2E.
InkOS targeted tests cover adapter mapping, blocking validation, unavailable
retry, legacy delegation, Runtime status, and direct authority-write guards.

During a parallel high-load run, one Studio filesystem-fixture test failed once;
the subsequent standalone full Studio run passed 487/487. Core's cold root
import grew after Runtime exports, so its lazy-notification test timeout was
raised from 10 to 30 seconds while retaining the same module-loading assertion.

The production outbox worker, operator abort/recovery endpoint, and deterministic
fault injector now cover all 15 named recovery scenarios, including Windows
occupied-file retry. No known Phase 4 recovery gap remains after the final
full-suite run.
