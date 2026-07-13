# RC-1A 本地章节来源清单

## 搜索方法

在当前 InkOS 与 Story Runtime snapshot 中，对生产源码和测试分别搜索了以下词族，并继续追踪到最终文件、DB 表或 HTTP endpoint：

```text
loadChapterIndex chapterIndex chapters/index.json .md readChapter listChapters
latestChapter chapterCount StateManager memory.db exportArtifact analytics
chapterPath readdir glob existsSync readFile readFileSync legacy fallback
shadow runtime authorityMode
```

`runtime`、`shadow`、`.md`、`readFile` 等是高噪声词。CSS box-shadow、普通配置读取、短篇/Play/翻译文件、UI 文案和模型字段并不是章节事实源。下表按“文件 + 符号/调用簇”归类，而不是把同一调用的 import、声明和使用重复列为多个来源。所有生产匹配均已归类，最终 `unknown = 0`。

## Runtime authority 生产读取：不合规本地来源

这些路径可在 Runtime authority 长篇项目中被调用，并让本地文件决定章节存在性、正文、数量、统计、搜索或导出集合。

| 文件 / 符号 | 匹配词 | 最终数据源 | 消费 surface | 风险 |
|---|---|---|---|---|
| `packages/core/src/state/manager.ts:468-524` `loadChapterIndex/rebuildChapterIndexFromFilesAt` | `loadChapterIndex`, `chapters/index.json`, `readdir`, `.md`, `readFile` | `books/<id>/chapters/index.json`；空/缺失时扫描 Markdown | 几乎所有旧读路径 | 核心静默 fallback；无 authority 分支 |
| `manager.ts:450-465` `getPersistedChapterCount` | `chapterCount`, `readdir`, `.md` | 本地章节文件名集合 | CLI status | 本地 count 可与 Runtime 矛盾 |
| `packages/core/src/state/durable-story-progress.ts` | `fallback`, `readFile`, `readdir`, `index.json`, `.md` | 本地 index/Markdown/显式 metadata | Studio dashboard、book list、bootstrap | 首页可显示 0/2/4 章 |
| `packages/studio/src/api/server.ts:1568-1575,2812-2820` | `StateManager`, `loadChapterIndex` | 本地 durable progress/index | dashboard、project summary、chapter list/recent | Runtime 项目错误 owner |
| `server.ts:3104-3111` | `analytics`, `loadChapterIndex` | 本地 index | Studio analytics | 错统计集合 |
| `server.ts:5148-5169` | `exportArtifact` | shared local exporter | Studio export | stale/幽灵正文可导出 |
| `packages/core/src/interaction/export-artifact.ts:58-130` | `loadChapterIndex`, `readdir`, `.md`, `readFile` | 本地 index + Markdown | Studio/CLI/TUI/agent export | 严重；没有 Runtime adapter |
| `packages/cli/src/commands/analytics.ts` | `analytics`, `loadChapterIndex` | 本地 index | CLI stats/analytics | 静默 stale |
| `packages/cli/src/commands/export.ts` | `exportArtifact` | local exporter | CLI export | 静默 stale |
| `packages/cli/src/commands/status.ts:47-98` | `loadChapterIndex`, `latestChapter`, `chapterCount` | Runtime latest + 本地 index/MD | CLI inspect/status | 单响应双源 |
| `packages/cli/src/commands/book.ts` | `loadChapterIndex`/next chapter | 本地 durable progress | book list | 错进度 |
| `packages/cli/src/commands/review.ts` | `loadChapterIndex` | 本地 index | review list/approve flows | 章节集合错误 |
| `packages/cli/src/commands/detect.ts` | `loadChapterIndex`, `chapterPath`, `readFile` | 本地 index/Markdown | detect | 漏章/幽灵章 |
| `packages/cli/src/commands/write.ts` | `loadChapterIndex`, `readChapter`, local rollback | 本地 index/Markdown | rewrite/sync/repair/auto gate | Runtime authority 行为分裂或失败 |
| `packages/core/src/pipeline/runner.ts:826-839` `getBookStatus` | `loadChapterIndex` | 本地 index | project status/shared tools | 错 summary |
| `runner.ts:1067-1090` | `loadChapterIndex` | 本地 title collection | Runtime write pre-validation | stale 标题影响去重 |
| `runner.ts:1201-1208` | `readdir`, `.md`, `readFile` | 最近本地 Markdown | paragraph drift comparison | Runtime 正文缺失时质量判断错误 |
| `runner.ts:1700-1708` `assertNoPendingStateRepair` | `loadChapterIndex`, `latestChapter` | 本地 index | write gate | stale 状态可错误阻止/放行 |
| `runner.ts:2051-2062` `readChapterContent` | `readdir`, `.md`, `readFile` | 本地 Markdown | sync/rewrite/revise 辅助路径 | Runtime 当前正文未被读取 |
| `packages/core/src/pipeline/scheduler.ts:369+` | `readdir`, `.md`, `readFile` | 本地 Markdown | daemon detection/background job | 后台处理 stale 正文 |
| `packages/core/src/utils/book-eval.ts:81-120` | `loadChapterIndex`, `readdir`, `.md`, `readFile`, `analytics` | 本地 index + Markdown | eval/quality stats | 统计与正文双误读 |
| `packages/core/src/interaction/project-tools.ts` | `loadChapterIndex` / durable progress | 本地 index/MD | TUI/agent project status | 共享入口传播 stale 数据 |
| `packages/core/src/interaction/edit-controller.ts` | `loadChapterIndex`, chapter file read | 本地 index/Markdown | chat edit/read | Runtime 项目不应把 projection 当当前正文 |
| `packages/core/src/agent/agent-tools.ts:2440-2486` grep tool | `search`, `readdir`, `.md`, `readFile` | 递归扫描本地 `story/`、`chapters/` | Studio chat/CLI interact/TUI search | D 可搜到幽灵章，C 漏 Runtime 章 |

## Runtime authority 生产读取：合规 Runtime 来源

| 文件 / 符号 | 最终数据源 | 说明 |
|---|---|---|
| `story-runtime/src/story_runtime/chapter_commits.py:116-128` | `chapter_commits` + `chapter_artifacts`, `state='FINALIZED'` | 权威单章读取，含 title/body/summary/checksums/revision |
| `story-runtime/src/story_runtime/api.py:282-286` | 上述 service | `GET /projects/{id}/chapters/{number}` |
| `inkos/packages/core/src/story-runtime/client.ts` `finalizedChapter` | Runtime HTTP | TypeScript DTO 校验后返回单章 |
| `studio/src/api/server.ts:2936-2951` | Runtime HTTP | Runtime authority detail 正确；error mapping 不正确 |
| `core/src/story-runtime/context-provider.ts` | Runtime `/queries/context` | 生成上下文合规，但不是产品 search/list |
| `core/src/pipeline/runner.ts:892-896` | Runtime `projectStatus.latest_chapter` | 写下一章章号正确由 Runtime 决定 |
| `core/src/pipeline/chapter-persistence-port.ts` 及 `story-runtime/chapter-persistence.ts` | Runtime prepare/validate/commit | Runtime authority 写入正确 |
| Runtime observability clients / Studio Runtime Panel | Runtime commits/events/projections tables | history/diagnostics 合规，但不能替代章节 collection read model |

## Legacy 项目读取

以下本地读取在 `authorityMode=legacy` 且迁移前是允许的，但必须被 `LegacyChapterReadAdapter` 隔离，不能因兼容而用于 Runtime authority：

| 文件簇 | 用途 |
|---|---|
| `state/manager.ts` index/Markdown reader | legacy 章节列表、detail、count |
| `interaction/export-artifact.ts` | legacy export |
| `commands/analytics.ts`, `computeAnalytics` | legacy stats |
| `commands/review.ts`, `detect.ts`, `utils/book-eval.ts` | legacy review/detect/eval |
| Studio legacy detail branch `server.ts:2953-2958` | legacy Markdown detail |
| `pipeline/runner.ts` local reader/rollback helpers | 只可服务明确 legacy 流程；当前 legacy 长篇又被标为 read-only，需要后续按 ADR 收敛 |

## Importer

这些匹配读取外部或 legacy 章节是有意的输入行为，不是产品当前事实源：

| 文件簇 | 数据源 | 限制 |
|---|---|---|
| `packages/cli/src/commands/import.ts` | 用户指定 txt/md/directory | legacy import source |
| Runtime `migration_jobs.py` scanner/CIR/import | legacy InkOS index/Markdown/truth files | cutover 前允许；cutover 后不得重新作为 target owner |
| spinoff/fanfic parent sample in `pipeline/runner.ts:1609-1624` | parent book local Markdown | 作为创作输入；若 parent 是 Runtime authority，后续也应经 read port |
| style/material ingestion | 用户指定文本/素材 | 与 finalized collection 无关 |

## Exporter

| 文件 / 输出 | 分类 | 结论 |
|---|---|---|
| `interaction/export-artifact.ts` -> txt/md/epub | 产品 exporter | 对 legacy 合法；对 Runtime authority 不合规 |
| Runtime `outbox.py:107-117` -> projection Markdown | projection exporter | 明确 `non-authoritative projection`，合规 |
| Runtime `outbox.py:119-130` -> metadata snapshot | operational snapshot | 不是正文 export；不能给产品导出复用 |
| translation EPUB/exporter | 非长篇翻译模块 | RC-1 不修改，需独立 ADR 才纳入 |
| short-fiction full.md/export | 独立短篇模块 | 非 Runtime 长篇范围 |

## Cache / projection / backup

| 来源 | 谁创建 / 时机 | 可失败、可重建、checksum | 反向覆盖风险 | 产品误用 |
|---|---|---|---|---|
| Runtime Markdown projection | `OutboxWorker` 在权威 commit 后处理 `markdown.export` | 异步/可失败/可重试；header 含 `body_sha256` | 未发现反向写 Runtime | 当前写到 Runtime DB 旁 `projections/`，不是 InkOS chapters；产品未直接消费 |
| Runtime search index | outbox `search.index` | 异步/可失败/可从 FINALIZED artifact 重建 | 无反向覆盖 | 产品 grep 未使用它 |
| Runtime snapshot | outbox `snapshot.create` | 异步/可失败/可重建；含 commit checksums | restore 是受控 recovery，不是普通反向覆盖 | 不含正文，不能作为产品 export |
| InkOS `story/memory.db` | legacy memory/retrieval pipeline | 可重建的语义/时间记忆 | 当前 Runtime context 主路径不应由其决定章节存在或正文 | 不是 finalized chapter owner，但旧辅助流程仍可能读取 |
| InkOS truth Markdown / runtime artifacts | Composer/StateManager | 本地 projection/control docs | 不应覆盖 Runtime finalized body | 可作为上下文但不是章节 collection |
| backups | Runtime operations / SQLite backup | operational copy | 仅受控 restore | 不应成为普通读 fallback |

删除 Runtime 自有 projection 后，权威 DB 的 detail/status/commit 仍可工作，outbox 可重建；删除 InkOS 本地 index/Markdown 后，当前 Studio list/analytics/export 和共享 CLI/TUI actions 会失效或显示 0，证明产品错误依赖 InkOS 本地副本。

## Test fixture

以下路径中的命中统一分类为 test fixture / assertion，不是生产读取：

- `packages/**/src/__tests__/**`
- `packages/**/*.test.ts`
- `hybrid/story-runtime/tests/**`
- `.test-tmp-*` 与本次临时 fixture 目录
- Studio/CLI targeted tests 中构造的 `chapters/index.json`、Markdown、HTTP Runtime stub

这些测试当前主要验证旧路径行为或 DTO 契约；它们没有证明 Runtime authority 产品一致性。

## Dead code / lexical false positives

| 命中类型 | 分类理由 |
|---|---|
| Studio CSS `box-shadow`, Tailwind `shadow-*` | 纯样式，非 authority `shadow` mode |
| `fallback` 用于 UI 文案、LLM model fallback、默认字符串 | 不读取章节 |
| `readFile/readdir/existsSync` 用于配置、skills、radar、covers、Play、translation、short fiction | 与 Runtime 长篇 finalized collection 无关 |
| `chapterCount` 出现在 short-fiction prompt/model | 该模块独立生成完整短篇，不是长篇 Runtime 项目 |
| `memory.db` 出现在 interactive-film | 非长篇模块，RC-1 不修改 |
| 被当前 dirty snapshot 删除的旧 `chapter-persistence.ts`, `chapter-import-source.ts`, `state-bootstrap.ts` | deleted/dead in current snapshot；不能作为当前生产路径 |

## Unknown 收敛

初始搜索中的不明确匹配均已通过 import/caller/final source 追踪，最终没有未分类的生产章节来源：

```text
unknown = 0
```

“无 unknown”不等于“无风险”：上表明确列出的 Runtime authority 本地生产读取就是 RC-1 的实施范围。
