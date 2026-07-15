# RC-1 最终数据所有权矩阵

状态：RC-1D 收口后的生产读取合同。本文描述当前代码，不是迁移前基线。

| 数据 | Owner | 非权威副本 | 产品读取入口 |
| --- | --- | --- | --- |
| chapter collection | Runtime | local projection | `ChapterApplicationService` |
| chapter body | Runtime | export/cache | `ChapterApplicationService` |
| analytics base data | Runtime | analytics cache | `ChapterApplicationService` |
| export source | Runtime revision snapshot | final export file | Export service |

## 不变量

1. Runtime authority 项目的章节存在性、顺序、latest、正文、checksum、基础统计和导出集合只由 Story Runtime finalized revision 决定。
2. Studio、CLI、TUI、pipeline、agent/context、analytics 与 exporter 不自行选择 authority；它们通过 `ChapterApplicationService` 或其 ports 读取。
3. Runtime 不可用、合同错误、版本不匹配、未授权或数据库锁定时 fail closed，不调用 legacy adapter。
4. local projection 可删除、可冲突、可落后；这些状态不得改变产品结果，也不得反向 bootstrap Runtime。
5. 当前不提供 stale chapter cache 正式读取模式。`stale=false` 的产品结果必须来自本次 Runtime 读取；无 Runtime 响应就无当前结果。
6. `authorityMode=legacy` 仅用于尚未 cutover 的 legacy 长篇只读兼容和 importer 输入。Runtime project 永远不能选择该边界。

## Runtime revision snapshot

Export service 接收 `ChapterExportPort.exportSnapshot()` 返回的单一 Runtime revision snapshot，再生成 TXT/MD/EPUB 与 manifest。最终导出文件是交付物，不是后续产品读取 owner。manifest 至少记录 authority、project revision、snapshot ID、collection checksum、chapter count 和逐章正文 checksum。
