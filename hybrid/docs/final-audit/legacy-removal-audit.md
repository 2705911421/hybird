# 旧实现移除审计

总体：`PARTIAL`。长篇 Runtime 写入主链已 fail closed，但旧模式、旧文件读取和 exported dead API 仍大量存在；其中最严重的是本地 chapter index/Markdown 仍是产品输出路径。

| 搜索项 | 可达性 | 状态 |
|---|---|---|
| `write_truth_file` | 仅 skill 文档/测试提示，Agent prompt 不暴露 | PASS |
| Markdown bootstrap | Runtime 正常路径抛错；migration importer 可用 | PASS |
| legacy chapter persistence | 未发现 Runtime authority 生产调用；本地 export/list 仍活 | FAIL |
| `memory.db` authority | importer 只作 candidate evidence；旧 memory 模块仍存在 | PARTIAL |
| direct Truth/raw state/chapter PUT | chapter PUT 明确拒绝；legacy Truth UI 仍存在 | PARTIAL |
| direct event append | operator-scope API 可达 | PARTIAL |
| JSON authority/SQLite mirror | Runtime write 不使用；legacy/importer 保留 | PARTIAL |
| `executeEditTransaction` | 从 core index 导出，生产搜索无调用者 | PARTIAL（dead exported API） |
| StoryRuntime `shadow` mode | Zod 仍接受；CLI/production routes 拒绝 | PARTIAL（schema drift） |
| Claude plugin path | 仅 migration cleanup/gate/provenance | PASS |
| webnovel Dashboard | provenance-only、architecture gate 禁止 import | PASS |
| hidden fallback | Runtime authority 无 legacy write fallback | PASS |
| deprecated-but-live | outline/Truth/session compatibility reads 很多；需逐模块收敛 | PARTIAL |

## 静态架构门禁

`python hybrid/scripts/check_architecture.py`：PASS，10 authority rules + duplicate dashboard isolation。

- InkOS 无 Runtime SQL：PASS。
- Studio 无 Runtime DB file access：PASS。
- Agent 无显式 authority write tool：PASS。
- Runtime 无 LLM：PASS。
- 正常 Runtime 写入无 Markdown bootstrap：PASS。
- 长篇写入无 legacy persistence：PASS。
- write API 元字段完整：PASS。
- migration provenance：PASS。

门禁没有检查 Studio chapter list/analytics/export 的读取 owner，也没有检查 symlink realpath，因此门禁通过不代表整体架构通过。

