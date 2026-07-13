# Phase 7 actual-project acceptance

Date: 2026-07-13  
Result: **PASS — Phase 8 removal gate opened**

An actual, pre-existing InkOS long-form project outside the repository fixtures was exercised read-only against two disposable Runtime databases. The private path and manuscript content are intentionally redacted.

## Evidence

| Item | Result |
|---|---|
| Source label | `redacted-real-inkos-long-form` |
| Source inventory | 357 files; 3,381,847 bytes |
| Source fingerprint | `e94fb4bd93708f2e4fde415789b79035da41b2d92675ed00ebecbab232782e93` |
| Manifest digest | `ec5f5bdd32050ca667eb55f274c6c4d6050efb88491075131b097f58ace2e07f` |
| Chapters | 21 |
| Explicit decisions | 103; including 21 unique chapter candidates and 81 quarantined conflicting facts |
| Dry-run delta | +21 chapters, +85 documents, +202 facts, +1 narrative thread |
| Unmapped fields | 1, retained in the migration report |
| Chapter body/checksum coverage | 100% |
| Doctor | `ok`, 0 blocking findings |
| Replay | matched |
| Projection hash | `a4f1bd7492852c13799b6ee75c98dc1bc1e50cba78a2d94bcba64b653db651e4` |
| Chapter export digest | `dc1d6798e67f517e50ff91ddaf97795db58efd17aafadffcc61af7c0b5581640` |

Run A completed discovery, scan, decisions, dry-run, snapshot, import, verify, and Runtime rollback; the target project was removed and the job ended `ROLLED_BACK`.

Run B repeated the flow, performed explicit cutover to Runtime authority, verified doctor and all 21 readable chapters, stopped the application, restored the pre-cutover backup, and confirmed legacy authority plus a healthy doctor result. Rollback did not re-enable dual-write.

This evidence supplements the deterministic Phase 7 fixture suite. It contains no private source path or manuscript text.
