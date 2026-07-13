# “缝合怪”反向证明审计

总体：`FAIL`。系统不是纯机械 HTTP 拼接，但仍保留多个产品级重复 owner，已产生真实用户可见矛盾。

| # | 迹象 | 状态 | 证据 |
|---:|---|---|---|
| 1 | HTTP 连通但生命周期未统一 | FAIL | process manager 未接产品 |
| 2 | InkOS 写章后 Runtime 滞后 | PASS | Runtime authority 写章直接 commit，不先本地写 |
| 3 | Runtime 查事实、InkOS 写 Truth | PASS（Runtime book） | Truth/chapter PUT fail closed |
| 4 | 两套 review | PARTIAL | unified schema；legacy adapter/old audit DTO 仍在 |
| 5 | 两套 context provider | PARTIAL | Runtime context 为 authority；InkOS legacy memory/outline reads 仍大量存在 |
| 6 | 两套 chapter persistence | FAIL | Runtime commit + 本地 chapter files 仍分别驱动 read/export surfaces |
| 7 | 两套 migration model | PASS | InkOS/webnovel 共用 CIR |
| 8 | 两套 status Dashboard | PASS | webnovel dashboard隔离；Studio Runtime view 是同产品 |
| 9 | Python/TS 同域 schema | PARTIAL | contract test约束，但三份 schema存在 |
| 10 | feature flags组合不可预测 | PARTIAL | shadow schema/legacy governance 与生产拒绝语义不一致 |
| 11 | 修复需改两套实现 | FAIL | chapter list/export 与 Runtime commit 需跨 TS/Python/contract 修改 |
| 12 | authority mode 可随意切换 | PASS | CLI拒绝 retired mode；cutover受控 |
| 13 | 恢复靠猜文件 | PARTIAL | Runtime doctor/recovery好；post-cutover rollback靠外部 runbook |
| 14 | 文档边界与代码不一致 | FAIL | skill/docs称 state JSON/Markdown；hybrid目标称 SQLite；产品仍读 Markdown |
| 15 | adapter 掩盖重复实现 | PARTIAL | legacy review/session/outline adapters 多 |
| 16 | 上游更新可合并性 | NOT VERIFIED | 无真实 upstream merge rehearsal |
| 17 | 完整复制但少量使用 | PARTIAL | `webnovel-writer` 全目录仍在 provenance workspace，门禁禁止产品 import |
| 18 | 核心依赖 Claude Code | PASS | build/test/Runtime package独立 |
| 19 | 用户需理解两项目结构 | FAIL | 手动启动 Runtime、配置 URL/token、理解 local chapters vs Runtime |
| 20 | 删除任一上游目录即失败 | PARTIAL | webnovel directory可不进产品；InkOS当然是产品壳；未做删除演练 |

反向结论：commit authority 内核融合是实质性的；产品生命周期、章节展示/导出和历史查询没有完成融合，因此仍是“内核已重写，产品外围仍拼接”的状态。

