# RC-2B1D2 Test Evidence

## Focused suites

| Command | Result |
|---|---|
| `python -m pytest tests/unit/test_rc2b1d_doctor.py -q` | PASS, 23 tests |
| `python -m pytest tests/contract/test_rc2b1d_architecture_gate.py -q` | PASS, 22 tests |
| `python -m pytest tests/unit/test_rc2b1d_ownership.py -q` | PASS, 13 tests |
| `python -m pytest tests/migration/test_rc2b1d_legacy_first_write.py -q` | PASS, 26 tests |
| `python hybrid/scripts/check_architecture.py` | PASS |
| approved Doctor OpenAPI contract test | PASS |
| `python -m pytest -q --durations=10` | PASS, 230 tests, 161.1 s |

The initial full Runtime run had one contract failure because the new Doctor
summary fields were absent from the approved OpenAPI schema. The schema was updated
within the Doctor scope and the failing test passed. The final rerun passed all 230
collected tests with no failures or skips reported.

## InkOS

InkOS commands did not reach their tests because pnpm 11 dependency validation
failed as recorded in `RC-2B1D2-ENVIRONMENT-LIMITATIONS.md`. They are NOT VERIFIED,
not PASS.
