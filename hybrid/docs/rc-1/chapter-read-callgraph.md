# RC-1A 章节读取调用图

## 总览

当前产品不是统一读路径，而是按 surface 分裂：

```text
Runtime chapter commit
  -> Story Runtime SQLite (authoritative)
  -> outbox: Runtime 自有 Markdown / search / snapshot 投影

Studio detail
  -> StoryRuntimeClient.finalizedChapter()
  -> GET /projects/{id}/chapters/{number}
  -> Runtime SQLite FINALIZED artifact

Studio list / analytics / dashboard / export
CLI analytics / export / review / status detail
TUI shared actions / search / project summary
  -> StateManager / shared Core tools
  -> books/{id}/chapters/index.json
  -> 缺失或空时扫描 books/{id}/chapters/*.md
```

因此 Runtime authority 项目存在“Runtime 写入、本地文件决定多数读取结果”的双产品事实源。

## Studio

| 用户入口 | route / component | application service | repository/provider | 最终数据源 | authority 分支与 fallback | Runtime unavailable | stale 风险 |
|---|---|---|---|---|---|---|---|
| 项目首页 / dashboard / book list | `GET /api/v1/books`; `BookList`/Sidebar | `loadStudioBookListSummary` | `StateManager.getNextChapterNumber` -> `loadDurableStoryProgress` | 本地 `index.json`/Markdown/metadata | 无 Runtime authority 分支 | 仍显示本地值，无错误 | 高；可显示 `0 chapters` |
| project summary | `GET /api/v1/books/:id` | route 内直接组合 | `StateManager.loadBookConfig/loadChapterIndex/getNextChapterNumber` | 本地 index，空/缺失时扫描 Markdown | 无 authority 分支；扫描是静默 fallback | 仍返回本地列表 | 高 |
| chapter list / recent chapters | `BookDetail.tsx` 消费 `GET /api/v1/books/:id` | 同上 | 同上 | 本地 index/Markdown | 无 authority 分支 | 仍显示本地 | 高，含幽灵章或缺章 |
| chapter detail / reader | `GET /api/v1/books/:id/chapters/:num`; `ChapterReader.tsx` | route 内创建 client | `StoryRuntimeClient.finalizedChapter`（Runtime 项目） | Runtime `chapter_artifacts` + `chapter_commits(state=FINALIZED)` | 有正确 authority 分支；legacy 才读 Markdown | broad `catch` 错误地返回 `404 Chapter not found` | 正文低；错误语义高 |
| editor/save | `PUT /api/v1/books/:id/chapters/:num` | 无 | 无 | 无直接写入 | 当前返回 `410 LEGACY_LONG_FORM_READ_ONLY` | 阻止写入 | 不构成读取双源 |
| analytics | `GET /api/v1/books/:id/analytics`; `Analytics.tsx` | `computeAnalytics` | `StateManager.loadChapterIndex` | 本地 index | 无 authority 分支，index 空时扫描 MD | 继续统计本地 | 高 |
| export/download | `GET /api/v1/books/:id/export` | `buildExportArtifact` | `ExportStateLike.loadChapterIndex` + `readdir/readFile` | 本地 index + Markdown | 无 authority 分支；缺 MD 会跳过，缺 index 失败 | 可静默导出 stale 本地正文 | 严重 |
| export-save | `POST /api/v1/books/:id/export-save` | `PipelineRunner.exportBook` -> shared artifact | 同上 | 本地 index + Markdown | 无集中 authority 选择 | 同上 | 严重 |
| search | Studio chat/agent `grep` action | shared `agent-tools.ts` | 递归 `readdir/stat/readFile` | 本地 `story/` 与 `chapters/` 下 md/txt/json | 无 authority 分支 | 静默搜索本地 | 严重 |
| review page | `/books/:id/review...`; Runtime review proxy | Runtime review client（Runtime 项目）以及本地 index 驱动的章节入口 | Runtime review endpoints + 本地章节集合 | 混合 | review artifact 有 authority 分支，章节候选集合仍可来自本地 | proxy 能映射部分错误；列表仍可存活 | 中高 |
| history | Runtime Panel commits/events/history | `StoryRuntimeClient.commits/events` | Runtime observability | Runtime DB | Runtime-only，无本地 chapter fallback | 显式映射 unavailable | 低，但不能替代 chapter list |
| migration page | `LegacyMigrationWizard` -> migration proxy | Runtime migration service | legacy source scanner / Runtime migration tables | legacy 文件作为 importer source | 合理 importer；cutover 后目标应只读 Runtime | 显式错误 | 不应复用为产品读取 |

关键代码：`studio/src/api/server.ts:1568-1575, 2812-2820, 2936-2961, 3104-3111, 5148-5169`；`core/src/interaction/export-artifact.ts:58-130`。

## CLI

| 用户入口 | command | application service | provider / 最终数据源 | authority 分支 / fallback | Runtime unavailable | stale 风险 |
|---|---|---|---|---|---|---|
| list books / 章节进度 | `inkos book list` | command + `StateManager` | 本地 durable progress/index/Markdown | 无统一 Chapter service | 仍返回本地 | 高 |
| list chapters | 没有独立 `chapter list`；`status --chapters` 与 `review list` 承担列表 | command 内直接读取 | `loadChapterIndex` -> 本地 index/MD | status 仅顶层 count 部分读 Runtime | Runtime 项目仍列本地章节 | 严重；同一 JSON 可矛盾 |
| show chapter | 没有稳定独立 `chapter show` 产品命令；review/detect/revise 路径按需读章 | 各 command/PipelineRunner | 多数为本地 index/Markdown | 分散判断 | 依路径而异 | 高 |
| continue/write | `write next`, `draft`, `plan`, `compose` | `PipelineRunner` | 新章号在写主路径用 Runtime status；上下文走 Runtime query；部分校验仍读本地 | `runner.ts:896` 正确；`1067` 标题去重、`1201-1208` 段落漂移错误读本地 | Runtime client 失败则写主路径失败；不会 commit 到本地 | 写 authority 正确，预写语义可受 stale 影响 |
| rewrite/sync/repair | `write rewrite/sync/repair-state` | PipelineRunner/StateManager | 仍含本地 rollback/delete/readChapter 实现 | Runtime authority 的 `saveChapterIndex` 会报错，但命令层未统一隔离 | 不会可靠降级；可能中途失败 | 高，且行为不完整 |
| export | `inkos export` | `writeExportArtifact/buildExportArtifact` | 本地 index + Markdown | 无 authority 分支 | 可静默导出本地副本 | 严重 |
| stats/analytics | `inkos analytics` / `stats` | `computeAnalytics` | `loadChapterIndex` | 无 authority 分支 | 继续返回本地统计 | 严重 |
| inspect/status | `inkos status [--chapters]` | command 内组合 | Runtime `projectStatus.latest_chapter` + 本地 index/MD | 分裂；无统一 read model | 顶层 Runtime 标 unavailable，但其他字段继续本地 | 严重；A-E 中出现 count/list 矛盾 |
| doctor | `inkos doctor` | environment/runtime probes | Runtime health/config；不负责章节集合 | 无章节 fallback | 显式诊断 | 低 |
| search | agent/interact `grep` tool | shared agent tool | 本地递归文件扫描 | 无 authority 分支 | 静默使用本地 | 严重 |
| detect/eval/review | `detect`, `eval`, `review list` | command/Core utility | `loadChapterIndex` 与本地 Markdown | 无统一 adapter | 静默本地 | 高 |

`status.ts:47-98` 是可复核的同响应双源：`chapters` 可来自 Runtime `latest_chapter`，`totalWords`、审核状态和 `chapterList` 来自本地 index。

## TUI

当前 TUI 是 `packages/cli/src/tui/app.ts` 的对话式 dashboard，不存在可独立审计的完整 chapter browser、current chapter、statistics 或 export 组件。不能把需求清单中的这些 surface 当成已实现界面。

| 用户入口 | route/action | service/provider | 最终数据源 | unavailable 与 fallback |
|---|---|---|---|---|
| project status / books | TUI interaction kernel，`/books` 或自然语言 action | shared `project-tools` / StateManager | 本地 durable progress/index/MD；部分 Runtime status | Runtime 状态可显示失败，但章节摘要仍可能来自本地 |
| writing | TUI -> interaction action -> PipelineRunner | 与 CLI write 相同 | commit 是 Runtime；预写校验仍可能读本地 | Runtime 不可用时 commit 被阻止 |
| export | TUI/agent export action | shared export artifact | 本地 index + Markdown | 静默 stale export |
| statistics/search | TUI/agent actions | shared analytics/grep | 本地 index/文件树 | 静默 local fallback |

非 TTY 环境未执行真实交互式 TUI 自动化；此处结论来自共享 action 调用链和已执行的 CLI/TUI targeted tests，不声称打开了不存在的独立页面。

## Core 与后台任务

| 入口 | 调用链 | 最终数据源 | 分类与风险 |
|---|---|---|---|
| context builder | Composer -> `StoryRuntimeContextProvider.queryContext` | Runtime `/queries/context` | Runtime authority 主路径正确；该 API 是生成上下文，不是产品章节搜索 |
| chapter reader | Studio detail -> `StoryRuntimeClient.finalizedChapter` | Runtime FINALIZED artifact | 正确但只有单章 |
| generic `StateManager.loadChapterIndex` | 多个 surface -> index -> 空/缺失扫描 MD | InkOS 本地 | Runtime authority 生产误读根源 |
| exporter | `buildExportArtifact` -> index/readdir/readFile | InkOS 本地 | Runtime 项目错误 owner |
| analytics/eval | `computeAnalytics` / `evaluateBookQuality` -> index + MD | InkOS 本地 | Runtime 项目错误 owner |
| indexing | Runtime outbox `search.index` | Runtime DB `retrieval_documents` | 可重建投影；产品 search 未消费它 |
| search/RAG | agent `grep` -> local files；Runtime context retrieval -> DB | 双路径 | 产品 search 本地；生成上下文 Runtime |
| snapshot | Runtime outbox snapshot | Runtime project/commit metadata | 非正文 backup/export；可重建 |
| backup | Runtime operations/backup | Runtime DB | 正确，未发现反向以本地章覆盖 Runtime |
| migration/import | migration scanner/CIR -> Runtime import | legacy index/MD 是输入源 | importer 合理；cutover 后不可继续作为 owner |
| project opening/rescan/bootstrap | `listBooks/loadDurableStoryProgress`; project bootstrap | 本地 book config/index/MD | Runtime 项目打开时可得错误章数 |
| scheduler | daemon detection stage -> 本地 Markdown | InkOS 本地 | Runtime authority 后台误读 |
| fallback | `loadChapterIndex` catch/empty -> scan MD | InkOS 本地 | 静默，且没有 stale 标记 |

## Runtime unavailable 行为实测

使用临时 Runtime authority fixture（本地保留 2 章）分别模拟 stopped/unavailable、timeout、malformed DTO、DB locked：

| surface | 实际结果 |
|---|---|
| Studio detail | 四种情形均被 broad catch 错误映射为 `404 Chapter not found` |
| Studio list | `200`，继续静默显示本地 2 章 |
| analytics | `200`，继续统计本地 2 章 |
| export | `200`，继续导出本地 stale Markdown |

Runtime 返回语义版本 `9.9.9` 但 DTO 兼容时，Studio detail 仍 `200`。`StoryRuntimeClient` 只做 DTO schema 校验，不比较 `runtime_version`；dirty `process-manager.ts` 有 handshake 版本/schema 检查，但只覆盖由 process manager 启动的进程，不是所有 application read 的强制门。

## A-E 一致性矩阵

Runtime 合同固定为 `revision=7, chapters=3, latest chapter=3`。真实临时 Runtime DB 已成功创建并 commit 3 章；长矩阵的进程型实测后段因连接 reset 中止。随后用严格匹配当前 Runtime DTO 的本地 HTTP stub 完成产品读取选择矩阵。

| Case | Studio list / analytics / summary | Studio detail | Studio / CLI export | CLI status |
|---|---|---|---|---|
| A 无 index/MD | 0 章 | Runtime 第 2 章正确 | 失败：无章节 | 顶层 3，本地统计 0 |
| B 空 index | 0 章 | Runtime 正确 | 失败 | 顶层 3，本地统计 0 |
| C 本地 2 章 | 2 章 | Runtime 正确 | 导出本地 2 章 | 顶层 3，列表 2 |
| D 本地 4 章含幽灵章 | 4 章 | Runtime 正确 | 导出本地第 4 章 | `chapters=3` 且 `chapterList.length=4` |
| E 第 2 章正文 checksum 不一致 | 3 章，本地统计 | Runtime 正文正确 | 导出 divergent 本地正文 | 顶层 3，正文相关路径仍本地 |

搜索继承本地文件状态：D 会检索幽灵章，C 会漏掉 Runtime 第 3 章。TUI 继承共享 action 行为；未虚构完整浏览器/TUI 交互测试。
