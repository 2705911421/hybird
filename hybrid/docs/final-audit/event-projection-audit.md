# 事件、投影与时间旅行审计

总体：`PARTIAL`。事件 replay 与 hash 验证成立，但历史 revision 查询是伪实现，触发发布红线 19。

| 检查 | 状态 | 证据 |
|---|---|---|
| commit 事件 append-only | PASS | event 主键/commit transaction；无 update/delete 正常路径 |
| deterministic event ID | PASS | commit 派生 ID 与 duplicate test |
| commit/chapter/ordinal/evidence/schema | PASS | event schema/migrations/commit tests |
| 普通写章不能 direct append | PASS | operator scope required，`chapter_commits.py:394` |
| reducer deterministic | PASS | replay hash unit/integration test |
| 空状态完整 replay | PARTIAL | core projection replay 有测试；全部历史 domain 未覆盖 |
| replay 两次 hash 一致 | PASS | unit test；12,000 events benchmark hash matched |
| projection failure 可恢复 | PASS | doctor + replay integration test |
| checkpoint 参与 replay | PARTIAL | checkpoint 表和参数存在；任意 checkpoint 恢复覆盖有限 |
| dry-run/verify-only | PASS | `verify_only` replay API |
| replay 不改 event | PASS | verify replay tests |
| 任意 revision 历史查询 | FAIL | 见下方 |
| migration provenance | PASS | CIR provenance 与 migration tests |

## 历史查询缺陷

`api.py:276-280` 接受 `at_revision`，但只拒绝“未来 revision”，随后仍调用 `services.entity(...)` 返回当前 entity。`repository.get_entity()` 不接收 revision，`include_history` 只返回当前 row 的 `history_json`。

因此：

- 人物第 N 章位置：FAIL。
- 关系在某 revision 状态：FAIL。
- 伏笔建立/回收历史：PARTIAL（事件可检索，但没有统一 revision state query）。
- 资源值随 revision 变化：FAIL。

这不是“未提供接口”，而是参数存在但语义未实现，属于更高风险的伪时间旅行。

## 规模实测

- 12,000 events replay verify：`1120.01 ms`。
- projection hash：`e02cf91...c4e7f08`，matched `true`。
- 数据集：1,096,328 中文字符、600 章、24,002 facts。
- 删除所有可重建 projection 后再建：仅测试覆盖，未在该 million DB 上单独破坏/重建，`NOT VERIFIED`。
- projection corruption + doctor/replay：小型 integration fixture `PASS`。

结论：发布红线 19 已触发；不能声称支持可靠时间旅行。

