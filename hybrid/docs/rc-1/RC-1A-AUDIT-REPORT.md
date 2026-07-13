# RC-1A 统一产品事实源实施前独立审计报告

## 审计结论

```text
IMPLEMENTATION BLOCKED BY RUNTIME API GAPS
```

Story Runtime 已经是 Runtime authority 长篇项目的写入 owner，并能权威读取单章 finalized artifact；不需要 fundamental ownership redesign。但当前产品多数章节 collection 读取仍由 InkOS 本地 `chapters/index.json` 和 Markdown 决定，同时 Runtime 缺少章节列表、分页、批量正文/导出、analytics aggregate 和产品 search API。RC-1 实施应先补 Runtime application-level read model。

本报告基于根仓库 `master@d727dd4cd0589bdb856046e92994fa8a5141ef46` 与 InkOS `master@fd87b04c3fbac7ab6ebc1b022fa117ee8051825e` 的 **dirty snapshot**。详细未提交文件见 `product-authority-audit-baseline.md`。

## 所有权标准

Runtime authority 长篇项目中，下列数据唯一产品 owner 必须是 Story Runtime：finalized chapter collection、number/title/body/checksum/summary/commit state、latest chapter、project revision、ordering/list，以及 analytics/export/search 和 Studio/CLI/TUI 的展示结果。

本地文件只能是 export/cache/projection/backup/legacy import source/临时文件，不得独立决定某章是否存在、当前正文、总章数、导出/统计/搜索集合或 latest chapter。

## 当前真实读路径

| 产品 surface | 当前 owner | 判断 |
|---|---|---|
| Runtime chapter commit | Story Runtime SQLite | 正确 |
| Studio chapter detail | Runtime finalized chapter API | 正确读取；错误映射有缺陷 |
| Studio chapter list/recent/project summary/dashboard | InkOS local index/Markdown | 不合规 |
| Studio analytics | InkOS local index | 不合规 |
| Studio/CLI/TUI export | InkOS local index + Markdown | 严重不合规 |
| CLI status | Runtime latest + local list/stats | 同响应双源 |
| CLI review/detect/eval/book list | InkOS local index/Markdown | 不合规 |
| write next chapter number/commit | Runtime status + Runtime persistence | 核心正确 |
| write title dedupe/paragraph drift/state gates | 部分 local index/Markdown | 不合规辅助读取 |
| TUI project/export/search/stats | shared Core actions，最终多为 local | 不合规；无独立完整 browser |
| product search | local recursive grep | 不合规 |
| generation context | Runtime `/queries/context` | 正确，但不是产品 search |
| Runtime projections/history | Runtime DB/outbox | 合规运维/投影路径 |

## 双源证据

1. `StateManager.loadChapterIndex` 直接读 `chapters/index.json`；文件缺失或数组为空时，静默扫描 Markdown 重建，没有 authority 分支（`manager.ts:468-524`）。
2. Runtime authority 仅禁止 `saveChapterIndex` 写入本地 index（`manager.ts:527-535`），却没有禁止从该 index/Markdown 读取。
3. Studio `GET /api/v1/books/:id`、analytics 和 export 分别在 `server.ts:2812-2820, 3104-3111, 5148-5169` 走本地路径。
4. `buildExportArtifact` 在 `export-artifact.ts:68-118` 从本地 index 选择章，再 `readdir/readFile` Markdown。
5. Studio detail 在 `server.ts:2943-2951` 正确调用 Runtime，造成同一页面的列表来自本地、正文来自 Runtime。
6. CLI status 在 `status.ts:47-98` 让顶层 `chapters` 来自 Runtime latest，而 totalWords/review counts/chapterList 来自本地。
7. agent search 在 `agent-tools.ts:2440-2486` 递归扫描本地文件，不调用 Runtime search。
8. Runtime commit 在 `chapter_commits.py:219-280` 原子持久化正文、summary/checksum/revision/latest chapter，证明权威写模型已经存在。

## 产品可见错误

确定性合同：Runtime `revision=7`、3 章、latest=3。

| 本地状态 | 实际产品结果 |
|---|---|
| A 无 index/Markdown | Studio list/analytics/summary 为 0；detail 正确；export 失败 |
| B index 为 0 | Studio 仍为 0；detail 正确；export 失败 |
| C local 2 章 | list/analytics/export 只有 2 章，漏 Runtime 第 3 章 |
| D local 4 章 | 幽灵第 4 章进入 list/analytics/export/search；CLI 同时报告 count 3/list 4 |
| E 第 2 章正文不同 | detail 返回 Runtime 正文，export 返回 divergent 本地正文 |

这直接重现并解释了“Studio 0 chapters，而 Runtime latest chapter 3”。

## Runtime unavailable 行为

对 stopped/unavailable、timeout、malformed DTO、DB locked 的临时 fixture 实测：Studio detail 均错误返回 404；list/analytics 继续静默显示本地 2 章；export 继续 `200` 导出 stale Markdown。Runtime version `9.9.9` 但 DTO 兼容时 detail 仍 `200`，说明 application read 没有统一版本 gate。

这些行为违反 fail-closed 要求。正确策略是 typed unavailable/timeout/locked/version mismatch/contract mismatch，阻止写入；只有经过校验且明确标 stale 的只读 cache 才可展示，且不能无提示 export。

## Runtime API 缺口

已有且可复用：project status/revision/latest、单章 detail/body/title/summary/checksums/revision、commit/events cursor pagination、generation context、observability、FINALIZED filtering。

缺失且阻塞实施：

- finalized chapter list 与 cursor pagination；
- authoritative chapter count、metadata-only list、ordering；
- list by volume/range；
- fixed-revision batch body/export stream；
- analytics aggregate；
- product search；
- list 级 deleted/aborted filtering contract；
- application-level read model。

commits/events/context endpoint 均不能替代章节 collection；逐章 detail 会造成 N+1、正文大 payload 和跨 revision 非一致快照。

## Runtime commit 后本地投影

Runtime commit 成功后把 `markdown.export`、`search.index`、`snapshot.create` 写入 outbox。`OutboxWorker` 明确称其为 disposable projections；失败不会回滚权威 commit：

| 投影 | 创建者/时机 | 失败与重建 | checksum / 反向覆盖 | 产品依赖 |
|---|---|---|---|---|
| Markdown | Runtime outbox，commit 后异步/显式 worker | 可失败、可重试、可由 DB 重建 | header 含 SHA-256；无反向覆盖 | 默认写 DB 旁 `projections/`，不是 InkOS chapters |
| search index | Runtime outbox | 可失败/重建 | 来源为 FINALIZED artifact | 当前产品 search 未使用 |
| snapshot | Runtime outbox | 可失败/重建 | 含 commit checksum；仅 metadata | 不能作为正文 export |
| InkOS index | Runtime 不创建 | 不适用 | 无 Runtime revision manifest | 当前产品却依赖 |
| analytics cache/export artifact/memory record | commit 后未发现 Runtime 自动创建 InkOS 对应物 | 不适用 | 不应反向覆盖 | 旧 product paths 仍直接读 local |

删除 Runtime 投影不影响权威 detail/status；删除 InkOS index/Markdown 会使当前 list/analytics/export 失效，进一步证明错误依赖。

## 迁移影响

| 项目类型 | RC-1 policy |
|---|---|
| Runtime authority 长篇 | 必须统一 Runtime adapter，无 local fallback |
| legacy 长篇 | migration 前由 Legacy adapter 只读 |
| migrated | cutover 后立即 Runtime-only read |
| partially migrated | cutover 前 legacy-only，cutover 后 Runtime-only；不得混合 |
| short fiction | 独立域，本 RC-1 不修改 |
| Play / interactive film | 独立域，本 RC-1 不修改 |
| translation | 独立域，本 RC-1 不修改 |
| exporters/plugins | 只要消费长篇章节集合，就必须经 ChapterApplicationService；其他域保持原 ADR |
| tests | 旧本地 fixture 继续服务 legacy adapter；新增 Runtime authority 矩阵 |

不得为了 legacy compatibility 让 Runtime 项目继续双源。

## 受影响文件

主要实施文件（当前 snapshot，按职责分组）：

- Runtime API/read model：`hybrid/story-runtime/src/story_runtime/api.py`, `contracts.py`, `chapter_commits.py`, `repository.py`, `services.py`, `observability.py`, `outbox.py`，以及对应 tests。
- Core authority/client：`inkos/packages/core/src/story-runtime/client.ts`, `schemas.ts`, `context-provider.ts`, `chapter-persistence.ts`, `process-manager.ts`。
- Core local reads：`state/manager.ts`, `state/durable-story-progress.ts`, `interaction/export-artifact.ts`, `interaction/project-tools.ts`, `interaction/edit-controller.ts`, `pipeline/runner.ts`, `pipeline/scheduler.ts`, `utils/book-eval.ts`, `agent/agent-tools.ts`。
- Studio：`packages/studio/src/api/server.ts`, `pages/BookDetail.tsx`, `pages/ChapterReader.tsx`, `pages/Analytics.tsx`, dashboard/sidebar/review/runtime/migration pages 与 API tests。
- CLI/TUI：`packages/cli/src/commands/book.ts`, `status.ts`, `analytics.ts`, `export.ts`, `review.ts`, `detect.ts`, `write.ts`, `doctor.ts`, `packages/cli/src/tui/app.ts`, program/integration tests。
- Migration/import：Runtime `migration_jobs.py` 与 InkOS import commands 仅需明确 adapter/cutover 边界，不应被当成正常读路径重写。

完整匹配分类见 `local-chapter-source-inventory.md`。

## 推荐实施批次

1. Runtime chapter list/page/read model + contract tests。
2. Runtime export/batch、analytics、product search + fault contracts。
3. InkOS ChapterReadPort、Runtime/Legacy adapters、集中 selector。
4. Core shared consumers/background jobs/write prechecks。
5. Studio list/detail/error mapping/analytics/dashboard/review selector。
6. CLI/TUI/status/export/search/actions。
7. A-E、fault、projection deletion、真实 browser/TTY E2E。
8. 删除 Runtime authority 旧本地读路径与 rollout flags。

## 风险

- 在 Runtime API 前抢跑会产生 N+1 和非一致 revision。
- 复用 commits endpoint 会把内部 commit 状态错误映射为章节集合。
- broad catch 会继续隐藏 unavailable/DTO mismatch 为 404。
- local projection 没有统一 revision manifest，无法安全充当 cache。
- dirty snapshot 改动面大；实现前应冻结或明确合并基线，否则行号/行为会漂移。
- legacy tests 可能把旧本地行为固化为 Runtime authority 期望，需要按 authority 分层新增测试，而不是修改测试以掩盖失败。

## 验收标准

- Runtime authority 项目所有章节产品读取只经过 `ChapterApplicationService -> StoryRuntimeChapterReadAdapter`。
- route/component/command 中没有决定 adapter 的 authority 分支。
- A-E 的 Studio、CLI、TUI/shared actions、analytics、export、search、summary 均返回 Runtime 3 章，正文/checksum/order 一致。
- stopped/timeout/version mismatch/malformed DTO/DB locked 均 typed fail closed；不静默 local fallback。
- 删除临时 fixture 的本地 index、Markdown、analytics/search/export projections 后，在线产品语义不变。
- export manifest 固定 revision 并列出 per-chapter checksum。
- chapter list 有 cursor pagination、metadata-only DTO、total count、ordering 和 FINALIZED filter。
- Python/TypeScript contract fixtures 双向通过；真实 Runtime + Studio browser + CLI JSON + TUI action/TTY E2E 通过。
- legacy 项目 migration 前只读可用；cutover 后没有双源。
- short fiction、Play、interactive film、translation 未被无 ADR 地改变。

## 证据限制

- 已执行 Runtime `107 passed`、Core `60 passed`、Studio `136 passed`、CLI/TUI `25 passed`；现有测试未覆盖 authority 一致性矩阵。
- 真实临时 Runtime DB 成功构造 revision 7/3 finalized chapters，并生成 outbox 投影；进程型长矩阵后段因 connection reset 中止。
- A-E 和 unavailable 产品选择矩阵随后由严格匹配当前 DTO 的本地 HTTP Runtime stub 完成。
- 未对真实用户项目执行迁移或破坏性操作；临时目录已删除。
- 未声称完成真实 Studio 浏览器的全部交互或独立 TUI chapter browser 测试；当前 TUI 也不存在该完整独立 surface。

## 最终判断

权威写模型成立，双源问题真实且产品可见。RC-1 可以按推荐架构实施，但必须先关闭 Runtime application-level read API 缺口；在此之前，不应通过兼容层、本地 fallback 或 route 内拼 endpoint 宣称统一事实源完成。
