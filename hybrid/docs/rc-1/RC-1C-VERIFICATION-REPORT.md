# RC-1C Verification Report

验证日期：2026-07-14  
验收对象：RC-1B 统一产品事实源  
最终结论：**RC-1 FAILED**

RC-1B 的部分 Runtime-backed 读取已在真实 Runtime、Studio API/Chromium 和 CLI 上观察到一致结果，但发布门禁要求的全部条件不成立。版本握手缺失、Runtime 不可用时仍接受写入、Runtime authority 写作链可达本地读取链、TUI 产品面缺失、全量测试失败以及 CI 未纳入关键 E2E，均足以阻断发布。

## 1. 黑盒产品矩阵

Runtime fixture：`project_id=rc1-verification`、`revision=7`、finalized chapters `1,2,3`、latest `3`。每个 local state 均执行 Studio 首页/list/detail/analytics/export/search、CLI list/show/stats/export、project reopen；TUI 的完整 browser/detail/stats 不存在，见未验证项。

| Local state | 本地扰动 | Studio/CLI 观察 | 判定 |
| --- | --- | --- | --- |
| 1 | 无 index、Markdown、analytics cache | count `3`，latest `3`，revision `7` | pass |
| 2 | index=`0` | 同上；Runtime 胜出 | pass |
| 3 | index=`2` | 同上；Runtime 胜出 | pass |
| 4 | index=`4` 且本地伪第 4 章 | 仍只有 `1,2,3`；伪章未进入 list/search/export | pass |
| 5 | 第 2 章本地正文 checksum 冲突 | Runtime chapter 2 checksum `b8ea99c4…` | pass |
| 6 | 本地 latest=`99` | reload 后仍 latest `3`、revision `7` | pass |

Chromium Studio 结果：首页显示 3 章；chapter list 显示 1/2/3；chapter 2 正文来自 Runtime；analytics 显示 `3 / 50 / 17`；State 6 reload 后仍显示 Runtime 3 章。截图和请求日志位于 `output/rc1-verification/`。

导出 manifest 在六种状态均为 `authority=runtime`、`projectRevision=7`、`chapterCount=3`、collection checksum `34b88b4013435d7e…`，chapter 2 checksum 与 Runtime 一致；本地伪章不在导出物中。CJK 标题/正文在 fixture 中正确传输。未能以真实超大项目证明内存上限或并发 commit 隔离，见未验证项。

## 2. 跨 surface 记录

| 项目 | Studio | CLI | TUI | Runtime |
| --- | --- | --- | --- | --- |
| chapter count | 3 | 3 | 启动摘要路径可显示 Runtime summary；无 browser/detail/stats surface | 3 |
| latest | 3 | 3 | 启动摘要使用 latest | 3 |
| chapter 2 hash | `b8ea99c4…` | `b8ea99c4…` | 未提供 detail view，无法记录 | `b8ea99c4…` |
| revision | 7 | 7 | 启动摘要显示 revision | 7 |
| export chapter count | 3 | 3 | 无 export view/command | 3 |

因此不能宣称 Studio、CLI、TUI 三者完整 parity；TUI 只覆盖启动摘要/聊天，不具备本任务要求的 browser/detail/stats 产品 surface。

## 3. 删除投影测试

在临时 fixture 中依次删除 local Markdown、index、analytics cache、search index、export cache。book 目录最终仅剩 `book.json`。chapter list/detail、analytics、search、export 仍正常；Runtime DB SHA-256 未变化；未生成 Markdown/index/cache，也未触发 Markdown bootstrap。该项通过。

## 4. Runtime unavailable 矩阵

| 故障 | Studio | CLI | 结果 |
| --- | --- | --- | --- |
| stopped / connection refused | 503 | exit 1 | 无本地旧数据泄漏 |
| timeout | 503 `RUNTIME_TIMEOUT` | exit 1 | fail closed |
| malformed response | 502 `RUNTIME_CONTRACT_MISMATCH` | exit 1 | fail closed |
| explicit version error | 502 `RUNTIME_VERSION_MISMATCH` | exit 1 | fail closed |
| degraded response | 503 | exit 1 | fail closed |
| `423 DATABASE_LOCKED` | 423 | exit 1 | fail closed |
| authorization failure (`401`) | 映射为 `RUNTIME_UNAVAILABLE`、retryable=true | exit 1 | 分类语义不准确 |

Runtime 停止时，`POST /api/v1/books/rc1-verification/write-next` 仍返回 HTTP 200 `{"status":"writing"}`；虽 2 秒后 Runtime DB 和本地文件未变化，但接口接受写入违反“不可写”要求，属于 blocker。Runtime 恢复并 reload 后回到 3 章/revision 7。未观察到静默读取 fallback；stale cache 显著标识和所有故障类型的自动刷新未完整验证。

## 5. 静态调用链证据

静态搜索覆盖 chapter index、Markdown reader、exporter、analytics、Studio routes、CLI commands、TUI、startup、context、search、fallback 和 authority resolver。匹配项分类如下：

| 位置 | 证据 | 分类 | 影响 |
| --- | --- | --- | --- |
| `inkos/packages/core/src/chapter-application-service.ts:275-302` | `LegacyChapterReadAdapter` 读取 `loadChapterIndex`、`readdir(chapters)`、`readFile` | legacy only | 可达但仅用于明确 legacy 项目；通过 |
| `inkos/packages/core/src/chapter-application-service.ts:263-271` | Runtime analytics DTO 只返回基础计数并硬编码 `auditPassRate: 100` | Runtime authority reachable | Runtime per-chapter/timestamps/volume aggregate 未向产品暴露，major |
| `inkos/packages/core/src/pipeline/runner.ts:707-738` | `planChapter`/`composeChapter` 调用 `state.getNextChapterNumber(bookId)` | Runtime authority reachable | 本地 index/Markdown 仍影响 Runtime 写作章节号，blocker |
| `inkos/packages/core/src/story-runtime/client.ts:139-141` | 存在 `health()`，但读取 service 链未调用 | Runtime authority reachable | 版本握手缺失；health 返回 Runtime `9.9.9` 时 Studio/CLI 仍 200/exit 0，blocker |
| `hybrid/story-runtime/src/story_runtime/chapter_reads.py:232-242` | export `fetchall()` 后构造完整 `chapters` 数组 | Runtime authority reachable | 大项目正文无界加载，major |
| `inkos/packages/cli/src/tui/app.ts:93-133` | TUI 启动只读取 summary/latest/review | Runtime authority reachable | 没有要求的 browser/detail/stats 视图，parity blocker |
| `inkos/packages/core/src/agent/context-transform.ts:135-187` 及写作 agents/planning materials | 读取 story Markdown、上一章正文、chapter summaries | Runtime authority reachable | 存在隐藏第二读取链，blocker |
| `LegacyChapterReadAdapter` 与 migration/import scanner | 本地 index/Markdown | legacy only / importer only | 不应被 Runtime authority 成功路径调用；静态可达写作链使门禁失败 |

`python hybrid/scripts/check_architecture.py` 和 `pnpm check:chapter-authority` 均通过，但它们未覆盖上述所有可达生产调用链，不能替代手工追踪。

## 6. Analytics、Search、Export

Search 在删除索引后可重建，伪第 4 章未出现，结果正文 checksum 回到 Runtime；本地冲突未改变 authority。Analytics 基础 chapter count/latest/total characters 在 fixture 中与 Runtime 一致，但产品 DTO 丢失 Runtime per-chapter size、timestamps、volume aggregate，且 `auditPassRate` 硬编码；cache revision 不一致的重建/stale 行为未完整覆盖。

Export 使用 finalized Runtime snapshot，manifest 带 revision 和 collection checksum；缺章、伪章、正文冲突均不改变 3 章结果。实现以 `fetchall()` 聚合完整正文，未满足大项目内存约束；真实导出期间 commit 的 revision 隔离和大项目分页未验证。

## 7. 测试与 CI

已通过：Runtime targeted/full pytest、Core targeted chapter/export tests、Studio `server.test.ts` 130 tests、typecheck、build、architecture gates。  
失败：全量 `pnpm test`，CLI 两个集成测试失败（English chapter count、degraded chapter count）。

`.github/workflows/rc1-chapter-authority.yml` 仅执行 install、`check:chapter-authority`、Core typecheck 和 Core mock-client test；没有 Chromium Studio、跨进程 deterministic E2E、CLI/TUI parity、Runtime unavailable 或删除投影 gate。关键 E2E 未进入 CI，触发发布门禁。

## 8. Blockers

1. Runtime health/version 未在读取链握手；错误 Runtime 版本仍返回产品数据。
2. Runtime unavailable 时 Studio `write-next` 接口接受 200 写入语义。
3. Runtime authority 写作 pipeline、context/agents 仍能读取本地 index/Markdown/上一章正文，存在隐藏第二读取链。
4. TUI 没有 browser/detail/stats/export 产品面，无法满足跨 surface parity。
5. 全量 InkOS 测试失败。
6. RC-1 CI gate 缺少关键 Studio/CLI/TUI Chromium 和 deterministic E2E。

## 9. Major / Unverified

Major：export `fetchall()` 无界加载正文；analytics DTO 丢失 per-chapter/timestamps/volume aggregates；401 被错误归类为 retryable unavailable；stale cache 显示/重建策略覆盖不足。

Unverified：真实超大项目内存峰值；真实 SQLite lock（本次验证的是合同 fault）；导出期间 commit 的原子 revision 隔离；TUI 完整浏览/详情/统计；所有 stale-cache 和恢复自动刷新组合；真实生产授权系统。

## 10. 判定

虽然六种本地状态、删除投影、Studio Chromium 关键读取和 CLI Runtime fixture 证明了部分 Runtime authority 行为，但发布门禁中的版本握手、不可用写入、隐藏本地读取链、TUI parity、全量测试和 CI E2E 均不满足。因此本次独立验收结论为：

**RC-1 FAILED**
