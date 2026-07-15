# RC-1 Final Data Ownership

## Runtime authority projects

| 数据/能力 | 唯一当前 owner | 允许存在但非权威 | 禁止作为 fallback |
| --- | --- | --- | --- |
| chapter collection/order/latest | Story Runtime finalized revision | local projection、export artifact | local index/Markdown |
| chapter body/summary/hash | Story Runtime chapter capability | export/cache artifact | local chapter files |
| recent narrative + Writer revision | Runtime revision-bound export/context | legacy source only in legacy mode | Writer filesystem reads |
| analytics base data | Runtime aggregate | presentation cache | local index-derived totals |
| search | Runtime search capability | display results | filesystem grep |
| export input | Runtime single-revision snapshot | generated TXT/MD/EPUB | stale local chapters |

Runtime unavailable、timeout、degraded、malformed DTO、version mismatch、authorization 与 DB locked 都终止当前 operation。Studio、CLI、TUI、Writer 和 exporter 不允许改选 legacy adapter，也不允许展示或导出旧 projection 冒充当前数据。

## Legacy/import/export boundary

- `authorityMode=legacy` 的未迁移项目可由明确的 Legacy adapter 读取 local index/Markdown；这不是 Runtime fault fallback。
- importer 可读取显式选择的 source files，将其作为导入输入；导入文件不是当前 Runtime authority。
- export projection 是交付物或可重建投影，不得反向成为产品读取 owner。
- Agent prompt 不暴露 Runtime DB path、table 或内部文件；Agent 只能消费 capability 返回的 typed context。

## Final invariants

1. Runtime authority 项目的 count/latest/revision/body/hash/analytics/search/export 必须来自同一 Runtime authority boundary。
2. local projection 可缺失、滞后、冲突或包含未来伪章，不得改变产品结果。
3. Writer narrative 与 status revision 绑定；本地恶意文本不能进入 Writer input。
4. authority resolver 只在项目边界选择一次 adapter；fault path 没有第二条 owner edge。
5. Studio、CLI、TUI 与 Runtime 对 RC-1 fixture 返回 `count=3, latest=3, revision=7`、相同 chapter 2 hash 与 export count=3。
