# Phase 9 test report

Date: 2026-07-13. This report intentionally separates evidence states.

## Actually verified on this Windows workspace

- Million benchmark: 1,096,328 characters, 600 chapters, 24,002 facts, 12,000 events; 30/30 layer budgets compliant.
- 12,000-event replay verify: 768.743 ms, hash `e02cf91ba67361538e9c8ea03f3f91f88eab1c45d77ac306b52648f11c4e7f08`.
- Snapshot 967.480 ms; 23,703,552-byte database; query plans use Phase 9 indexes.
- Runtime full suite: 107 tests passed. Architecture gate: all 10 authority rules plus duplicate-dashboard isolation passed.
- Short soak smoke: 1.562 seconds, five iterations, zero errors, one intentional lock retry, one chapter commit and three completed outbox records. This is not the 24-hour qualification.
- InkOS root `pnpm typecheck`, `pnpm build` and final `pnpm test` passed. The final complete three-workspace test run ended successfully in 304.4 seconds; the CLI portion reported 38 files and 205 tests passed.
- Studio build retained the known large-chunk warning; the main entry was 2,527,362 bytes. Hash-route tests also passed 31/31 in the focused run.
- Playwright manual flow found then verified fixes for Runtime routing and polling; automated five-sample Studio benchmark completed and raw JSON is committed.
- Windows PyInstaller standalone build passed after its first smoke exposed and drove a fix for the `__main__` import. Final `--help` and real process `/health` smoke passed; the executable was 16,136,763 bytes with SHA-256 `0b508551bf539653151cac561e9b4610a3837e02123a2ca034835e09b8dc28ec`.
- The Node process manager then launched that real packaged executable, completed the health/schema handshake and stopped its full PyInstaller process tree without a leaked Runtime process. A crash-loop test also verified the configured restart ceiling.
- Offline installation passed on Windows: a fresh venv installed Runtime and all dependencies from a temporary wheelhouse with `--no-index`, migrated schema 0 to 7, and passed `pip check`.
- All four workflow YAML files parsed successfully. Request logging regression verified route-template operations and pseudonymized project IDs.
- Release license assembly was checked against the fixed webnovel-writer commit; the raw GPL text SHA-256 is `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`.

## Implemented/design complete, not yet environment-verified

- Windows/Ubuntu/macOS Python 3.11/3.13 and Node 22 CI matrices.
- Cross-platform offline wheel install and PyInstaller smoke, audit/secret/SBOM and release artifact workflows.
- Scheduled 24-hour soak workflow.
- Source archive/checksum/license/SBOM assembly and upstream sync process.

## Not verified because this environment cannot provide the evidence

- Windows clean-machine install and macOS/Linux build, install, package launch and signals. The Windows checks above ran in the development workspace.
- Windows installer signing, macOS notarization and Linux package-manager install/uninstall.
- 24-hour leak trend, handle/file/process leakage thresholds.
- Full forced-shutdown, ENOSPC, antivirus lock, corrupt DB/blob and failed app/Runtime upgrade drills.
- Optional real-model smoke; it is non-blocking and was not run.

## Known risks and release blockers

- Native one-click installer/package integration for the complete InkOS shell is absent; only portable artifacts and standalone Runtime are built.
- `StoryRuntimeProcessManager` implements discovery, handshake, PID ownership, restart/backoff and process-group shutdown, but the Studio/CLI product bootstrap does not yet instantiate it or select the bundled Runtime. App-managed one-click lifecycle is therefore not accepted.
- 24-hour soak has no completed report.
- Cross-platform workflows have not run for this working tree.
- Full SBOM/license inventory has not been generated and reviewed for the release commit.
- Combined App/Runtime compatibility DTO does not machine-emit every matrix label.
- Separate projection-only, lock-wait, outbox-lag and million-event Studio distributions are missing.
- Legal status in `UPSTREAM_PROVENANCE.yml` remains provisional.

Therefore Phase 9 must not be announced complete and release must remain blocked.
