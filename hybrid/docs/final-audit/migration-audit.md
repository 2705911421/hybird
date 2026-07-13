# 迁移审计

总体：`PARTIAL`。CIR、只读扫描、冲突、人为决策、中断恢复、幂等与 snapshot 都有强测试；cutover 后实现内 rollback 被明确拒绝，触发发布红线 9。

| 检查 | 状态 | 证据 |
|---|---|---|
| source 只读 | PASS | immutable/read-only SQLite、checksum drift tests |
| versioned CIR；两源同模型 | PASS | `canonical-import-v1.json`、migration service |
| dry-run/coverage/checksum | PASS | Phase 7 integration tests |
| conflict quarantine，不自动选 | PASS | semantic conflict tests |
| pause/resume/idempotent rerun | PASS | batch checkpoint/no duplicate test |
| target snapshot verified | PASS | checksum + SQLite integrity |
| cutover 人工确认 | PASS | confirmation action/API |
| cutover 后 Runtime authority | PASS | `migration_jobs.py:252-270` |
| provenance/unknown fields | PASS | CIR provenance/unmapped fields |
| CJK/Windows path | PARTIAL | Windows/CJK fixture 本机通过；远端 Linux 因单组件超长 CJK 名失败 |
| symlink/zip slip/traversal | PASS | migration attack tests |
| corrupt JSON/SQLite | PASS | quarantine tests |
| chapter checksum/replay hash | PASS | mismatch + independent replay tests |
| pre-cutover rollback | PASS | snapshot restore test |
| post-cutover rollback | FAIL | `migration_jobs.py:273-276` 直接抛 `POST_CUTOVER_ROLLBACK_REQUIRES_STOP` |
| migration 后不回写源 | PASS | importer source read-only；Runtime authority fail closed |

测试：migration selection 共 14/14 PASS，覆盖正常 InkOS、JSON/Markdown 冲突、chapter gap、alias collision、webnovel JSON/SQLite 不一致、损坏源、中断恢复、重复执行、million fixture、Windows/CJK。

限制：million fixture 是 synthetic importer 能力，不证明源项目经历真实 InkOS 生命周期。Windows 长路径测试还把一个超过常见单文件名 255-byte 限制的组件作为 fixture，导致正式 Ubuntu CI 2 个测试失败。

结论：有可恢复的 pre-cutover snapshot 不等于 cutover 后可回滚。当前只给人工 runbook 提示，不是实现内、已测试 rollback；发布红线 9 触发。

