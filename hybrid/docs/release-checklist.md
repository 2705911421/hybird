# Phase 9 release checklist

Every checkbox requires a linked artifact. An absent artifact is not a pass.

- [x] Scope frozen; no new authority/domain/runtime introduced.
- [x] Deterministic million-character Windows benchmark recorded; token budget and 12k replay hash recorded.
- [x] Short soak harness runs in PR CI; 24h scheduled workflow exists.
- [ ] 24h million-scale soak completed within leak/error thresholds.
- [ ] Windows, macOS and Linux clean-machine portable package smoke artifacts accepted.
- [ ] Signed Windows installer, notarized macOS package and Linux package/uninstall behavior accepted.
- [x] Runtime standalone PyInstaller build recipe and package smoke workflow exist.
- [x] Windows development-workspace standalone build, `--help`, health and offline wheel-install smoke pass.
- [ ] Studio/CLI bootstrap owns the bundled Runtime process manager end to end, including crash recovery and shutdown.
- [x] Online snapshot/new-directory restore automated tests pass.
- [ ] Full corruption, missing blob, ENOSPC, force-power-off and upgrade-failure drill reports accepted.
- [x] Runtime is loopback-only; bearer is child-environment-only; route proxy does not expose it.
- [x] JSON logs are redacted, size-rotated and retention-bounded.
- [ ] Dependency audit, secret scan and generated SBOM workflows pass on release commit.
- [x] AGPL/GPL provenance, NOTICE and source archive workflow exist; the pinned webnovel-writer GPL text is checksum-verified during release assembly.
- [ ] Release artifacts include checksums, SBOMs, license bundle, source archive, Runtime and three OS packages.
- [ ] Final deterministic install-to-reinstall E2E scenario passes on all supported OSes.
- [ ] Maintainer/legal review clears provisional provenance status.

Release is blocked while any unchecked item above is required for the chosen artifact label.
