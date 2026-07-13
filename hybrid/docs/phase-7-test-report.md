# Phase 7 test report

Date: 2026-07-13

This report is updated from executed local checks; no real LLM or source script was used.

## Fixtures

`scripts/generate_phase7_fixtures.py` deterministically creates normal/large InkOS, Markdown-JSON conflict, chapter gap, CJK/emoji, Windows long path, corrupt JSON, corrupt SQLite, symlink escape, webnovel JSON/SQLite mismatch, alias collision, multi-volume and one-million-character synthetic cases. Generated bulk fixtures remain test-temporary rather than being committed as private creative data.

## Results

| Check | Result |
|---|---|
| Story Runtime full suite | 95 passed |
| Phase 7 Runtime integration | 12 passed |
| CIR/schema contract | 2 passed |
| fixture catalog/performance | 2 passed; 100 chapters and ≥1,000,000 source bytes scanned under the 15 s gate |
| Studio migration + Phase 6 proxy regression | 8 passed |
| InkOS Core Runtime/persistence regression | 15 passed |
| InkOS core typecheck | passed |
| Studio client/server typecheck | passed |

Covered behavior includes discovery, CIR schema, mapping, dry-run, SHA-256, source mtime preservation, post-scan checksum drift rejection, corrupt input, symlink and ZIP-slip rejection, explicit decisions that alter the effective CIR, selected chapter-body import, true import-ledger rerun idempotency, batched interrupt/resume from checkpoint, Unicode/CJK/emoji, JSON/SQLite disagreement, verified snapshot restore, independent CIR replay drift detection, explicit cutover, and Studio’s absence of a skip-all action.

`python -m pip check` reported no broken requirements. `compileall` passed. The final 95-test run used `--basetemp C:\tmp\phase7-pytest-20260713-final -p no:cacheprovider` after the default Windows temp/cache directories began returning ACL access errors. The environment also emitted warnings for unrelated third-party package metadata, and root `git diff --check` emitted permission warnings for protected `.test-tmp-*` directories while returning success; Phase 7 files had no whitespace errors.
