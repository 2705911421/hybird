# 章节事务与幂等审计

总体：`PARTIAL`。核心事务实现强，已跑故障矩阵没有发现未知半提交；但真实 disk-full 和完整 blob orphan 回收未执行，因此不能按用户给定标准写 PASS。

## 状态机与元数据

| 检查 | 状态 | 证据 |
|---|---|---|
| 9 个要求状态齐全 | PASS | `chapter_commits.py:37` |
| 转换持久化及 audit | PASS | `chapter_commit_transitions`；fault matrix |
| 非法跳转拒绝 | PASS | `test_chapter_commits.py` |
| request/idempotency/expected/resulting revision | PASS | schema + unit tests |
| schema/body/artifact checksum | PASS | validate token 与 checksum 检查 |
| response loss retry 同结果 | PASS | `test_state_machine_finalizes_atomically_and_retries_response_loss` |
| 同 key 不同 payload 冲突 | PASS | `test_same_key_different_prepare_payload_conflicts` |
| 并发同 revision 单赢家 | PASS | `test_concurrent_same_chapter_commit_has_one_winner` |
| event/authority/core projection 同事务 | PASS | `chapter_commits.py:219-280` |
| outbox 不参与 authority transaction | PASS | pending outbox fault test |
| 正文与 commit 原子可查 | PASS | finalized chapter checksum test |
| blob orphan 检测/回收 | NOT VERIFIED | 未找到独立 blob GC 验收证据 |

## 故障注入结果

`python -m pytest tests/integration/test_phase4_failure_matrix.py`：11/11 PASS。

| 场景 | DB/commit/revision/doctor 结果 | 状态 |
|---|---|---|
| prepare 后终止、重启 | durable PREPARED，可识别恢复 | PASS |
| validate 后终止、重启 | durable VALIDATED，可识别恢复 | PASS |
| transaction 中异常 | authority/event/projection 全回滚 | PASS |
| event append 异常 | 无 event/事实半写 | PASS |
| projection 异常 | 整个 commit 回滚 | PASS |
| finalize 前异常 | 可识别状态，无未知半态 | PASS |
| commit 成功 response loss | retry 返回同 commit/revision | PASS |
| Runtime/InkOS restart | idempotency 记录持久 | PASS |
| SQLite lock | retryable/可诊断 | PASS |
| 两个并发提交 | 一个成功，另一个 revision conflict | PASS |
| Windows 文件占用/outbox replace | retry 后完成，无 authority 回滚 | PASS |
| 磁盘写失败/disk full | 未真实执行 | NOT VERIFIED |

测试时未自动 repair 用户数据库。72 秒 soak 另完成 33 次 commit、0 error。

## 结论

没有证据触发“未知半状态”或“response loss 重复提交”红线。发布前仍需在隔离卷执行 ENOSPC/disk-full、正文存储损坏与 orphan 回收测试，并保存每一步 DB/doctor/revision 原始记录。

