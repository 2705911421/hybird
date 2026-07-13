# RC-1 产品事实源整改实施设计

## 目标与不可变约束

Runtime authority 长篇项目的 finalized chapter collection、编号、标题、正文、checksum、summary、commit state、latest chapter、revision、ordering/list，以及 analytics/export/search/Studio/CLI/TUI 的章节结果，唯一产品 owner 是 Story Runtime。

InkOS 本地章节文件只能是 export、cache、projection、backup、legacy import source 或非权威临时文件。任何 route、component、command 都不得单独决定 authority mode 或在 Runtime 失败时静默退回本地。

目标结构：

```text
Studio / CLI / TUI / background jobs
                 |
       ChapterApplicationService
                 |
          ChapterReadPort
          /             \
StoryRuntimeChapterReadAdapter   LegacyChapterReadAdapter
          |                              |
 Story Runtime product API        InkOS index/Markdown
```

adapter 选择只能发生一次：由项目打开/应用服务工厂根据经过校验的 authority mode 选择。`authorityMode=runtime` 必须选择 `StoryRuntimeChapterReadAdapter`，不得 catch 后选择 legacy。

## 1. 统一 application service

新增 InkOS Core `ChapterApplicationService`，作为所有产品 surface 的唯一章节读取入口。建议最小接口：

```ts
interface ChapterApplicationService {
  list(projectId, query): Promise<ChapterPage>;
  get(projectId, chapterNumber, options?): Promise<ChapterDetail>;
  latest(projectId, options?): Promise<ChapterDetail | null>;
  summary(projectId): Promise<ChapterCollectionSummary>;
  analytics(projectId, query?): Promise<ChapterAnalytics>;
  export(projectId, request): Promise<ChapterExport>;
  search(projectId, request): Promise<ChapterSearchPage>;
}
```

每个返回值必须携带 `authority`, `projectRevision`；任何 cache 结果还必须携带 `stale=true`, `cachedRevision`, `verifiedAt`。应用服务负责 error mapping、revision consistency 和 telemetry，UI/CLI 只消费 typed result。

## 2. Runtime API 缺口

在 InkOS 切换 list/analytics/export/search 前先交付：

- finalized chapter list + cursor pagination；
- authoritative total count、latest chapter、project revision 同快照返回；
- metadata-only DTO，避免正文大 payload；
- range/volume filters 与明确 ordering；
- snapshot-consistent batch body/export stream；
- analytics aggregate；
- product search API 与 index revision/stale contract；
- deleted/aborted filtering contract；
- typed unavailable/locked/migration/version/schema errors。

保留现有单章 detail，但补 ETag/expected revision 或 response revision 语义。不要让 Studio 通过 commits/events/projections 拼装 chapter list。

## 3. Studio 改动点

- `GET /api/v1/books` 的 `chaptersWritten` 改为 application service summary。
- `GET /api/v1/books/:id` 的 chapters/nextChapter 改为统一 read model。
- detail route 改用 application service，并保留 legacy adapter；移除 broad catch 的伪 404。
- Analytics、BookDetail、recent chapters、project summary、dashboard、review chapter selector、history links、export 全部消费统一 DTO。
- Runtime unavailable 页面显示 typed state、重试/诊断入口；不可继续显示未标 stale 的本地数字。
- component 不读取 `authorityMode` 来决定数据源；它只展示 service 返回的 authority/stale/error state。

## 4. CLI 改动点

- `book list`, `status --chapters`, review list, detect, eval 统一走 ChapterApplicationService。
- 增加/规范 `chapter list`、`chapter show`，不要继续让 status/review 隐式承担章节浏览。
- `status` 的 count、words、list 必须来自同一 revision；禁止当前“count=3/list=4”。
- `write/plan/compose/auto/rewrite/sync/repair` 的章号、最近正文、标题集合和状态 gate 统一从 service 读取。
- `doctor` 增加 adapter selection、Runtime contract version、projection freshness 检查，但不把本地 projection 可用视为 authority healthy。
- CLI error code 对 stopped/timeout/locked/version mismatch/malformed DTO 保持可区分。

## 5. TUI 改动点

- TUI 当前是共享对话 action surface，不先虚构独立 browser；先改 shared project/export/search/analytics actions。
- 若后续增加 chapter browser/current chapter/statistics，必须直接消费 ChapterApplicationService DTO。
- Runtime unavailable 以明确 banner/state 展示，写动作 disabled；不得把 local projection 当正常当前章。
- TUI 交互测试需真实 TTY harness 或可测试的 reducer/action layer，不能只用 CLI test 代替。

## 6. Analytics 改动点

- chapter count、word count、average、status distribution 的集合与 revision 由 Runtime aggregate 返回。
- review/audit 指标若仍在另一 owner，Runtime application read model 应按 chapter commit/revision 关联，而不是前端 join 本地 index。
- legacy adapter 可保留 `computeAnalytics(index)`，但 Runtime adapter 不得调用它。
- cache 必须标识 aggregate revision；不能对 stale cache 无提示展示。

## 7. Export 改动点

- Runtime authority export 必须从固定 Runtime revision 的 batch/stream 获取 title/body/checksum/order。
- txt/md/epub formatter 可以继续位于 InkOS，但输入必须是 Runtime export DTO/stream。
- export manifest 记录 project revision、chapter count、每章 checksum、generatedAt、authority。
- Runtime unavailable 时禁止静默导出本地 Markdown；只有用户明确选择“导出已验证的 stale cache”且产物显著标注时才允许。
- `approvedOnly` 的审批状态必须有 Runtime/read-model 合同，不能由本地 index 筛选。

## 8. Search 改动点

- 产品章节 search 使用 Runtime product search API；返回命中章节、片段、checksum/revision、page cursor、index revision。
- agent `grep` 对 Runtime authority 的 `chapters/` 路径必须被 ChapterApplicationService search 取代；仍可 grep 非章节 control docs。
- Runtime index degraded 时明确显示 degraded/stale，不得 fallback 搜本地 Markdown。
- RAG/generation context 与 product search 继续分开：`/queries/context` 不应冒充用户搜索。

## 9. 本地 projection 新职责

| projection | 新职责 | 必须携带 | 禁止用途 |
|---|---|---|---|
| Markdown | 人工检查、debug、明确 export/cache | revision、body checksum、non-authoritative header | 决定存在/正文/latest/count |
| chapter manifest/index | 可重建 cache/export manifest | project revision、collection checksum、verifiedAt、stale state | Runtime 项目正常 list owner |
| analytics cache | 性能 cache | aggregate revision、TTL/verifiedAt | 无提示展示当前统计 |
| search index | Runtime 管理的可重建 projection | indexed revision/health | 本地 grep 代替产品 search |
| snapshot/backup | 运维恢复 | manifest/checksum/createdAt | 日常读取 fallback |
| memory records | 生成上下文/retrieval | source revision/evidence | finalized body owner |

删除任一 projection 后，Runtime authority 的 list/detail/analytics/export/search 应能通过 Runtime 正常工作；性能可下降，但语义不能改变。

## 10. Legacy compatibility

- `authorityMode=legacy` 在迁移前由 `LegacyChapterReadAdapter` 只读提供 index/Markdown 行为。
- migrated/cutover 项目必须原子选择 Runtime adapter；不得保留 per-surface 双源。
- partially migrated 项目在 cutover 前仍是 legacy-only read，在 cutover 后 Runtime-only read；中间态明确显示 migration state，不混合拼接。
- legacy importer 继续可读本地源，但 migration target 一旦 Runtime authority，不得再次把源文件当产品 owner。
- 兼容代码位于 adapter 内，不散落在 route/command/component。

## 11. Fallback policy

| 情形 | Runtime authority 行为 |
|---|---|
| Runtime stopped/unreachable | 明确 unavailable；阻止写入；提供重启/doctor |
| timeout | typed timeout，可重试；不读 legacy adapter |
| version mismatch | 阻止读取/写入；显示升级指引 |
| malformed DTO | contract mismatch；阻止，保留诊断信息 |
| DB locked | typed locked；只允许重试/诊断 |
| local newer/older | 忽略为 owner；可在 diagnostics 报差异 |
| verified cache 存在 | 仅显式 stale/offline 只读；默认不得作为正常响应 |
| cache 校验失败 | 不展示正文/列表；明确失败 |

`fallbackOnUnavailable` 应退出或重定义为“允许显式 stale cache view”，不得表示切换到 legacy authority。

## 12. Feature flag 退出策略

1. 新 Runtime list/export/analytics/search API 先以 server capability negotiation 上线，不改变旧 surface。
2. `ChapterApplicationService` 与 adapters 落地，legacy 项目先接入以验证接口稳定。
3. Runtime authority 在测试/开发环境强制新 adapter，不提供 local fallback flag。
4. Studio/CLI/TUI 分 surface 迁移时使用 telemetry-only rollout flag；flag 只控制 UI rollout，不控制 authority 选择。
5. 所有矩阵和故障测试通过后，Runtime authority 旧读路径删除。
6. 删除/重定义 `fallbackOnUnavailable`，移除散布的 authority checks 和 rollout flags。

退出门槛必须由一致性测试和零旧路径调用证明决定，不能只依赖设计文档声明。

## 13. 测试计划

- Contract：Python Pydantic/OpenAPI 与 TypeScript Zod 对 chapter list/page/export/analytics/search 双向 fixtures。
- Adapter：Runtime 与 legacy adapter 同一 port contract；Runtime adapter 断言从不调用 StateManager chapter reader。
- Authority selector：runtime/legacy/migrating/cutover 的确定性选择；Runtime 失败不切 adapter。
- A-E：Runtime 固定 revision 7/3 章，本地无/0/2/4/divergent；所有 Studio/CLI/TUI/shared actions 结果均为 3 章。
- Fault matrix：stopped、timeout、version mismatch、malformed DTO、DB locked、local newer/older。
- Projection deletion：删除临时 fixture 的 index/MD/analytics/search/export projection，产品语义保持不变。
- Export：固定 revision、顺序、checksum、approvedOnly、range、大项目流式内存上限。
- Search：index revision、pagination、degraded/stale 表示、幽灵章排除。
- Migration：pre-cutover legacy-only，post-cutover Runtime-only，rollback 仅按 migration ADR。
- E2E：真实 Runtime process + Studio browser；CLI JSON；真实 TTY/action reducer TUI。

所有破坏性测试只在临时 fixture 运行，不触碰真实用户项目。

## 14. 回滚计划

- Runtime API 是 additive change，可回滚 InkOS consumer 而不回滚 Runtime authority 数据/schema。
- 每批 consumer 改动可独立回滚到上一批，但 **Runtime authority 不得回滚到 local owner**；如新 read adapter 有缺陷，应 fail closed、停 rollout，而不是启用 legacy fallback。
- legacy adapter 保留到 migration 退出完成，为未迁移项目提供只读兼容。
- DB migration 若新增 index/read model，应提供经过测试的向前修复路径；不得以回滚产品读取为由删除 Runtime chapter authority 数据。
- projection 可随时删除重建；回滚不依赖 projection 反写 Runtime。

## 15. 可分批提交顺序

1. Runtime chapter list/read-model DTO、repository query、cursor pagination、contract tests。
2. Runtime batch/export stream、analytics aggregate、product search 与 fault/error contracts。
3. InkOS `ChapterReadPort`、Runtime/Legacy adapters、selector、contract tests。
4. Core shared consumers：project summary、write prechecks、eval/review/detect/background jobs。
5. Studio list/detail/analytics/dashboard/review selector/history link error mapping。
6. Export formatter 输入切换与 manifest；CLI export/status/analytics/list/show。
7. TUI/agent project/export/search actions 与 unavailable UI。
8. A-E + fault + projection deletion 全产品 E2E。
9. 移除 Runtime authority 的 StateManager chapter reads、散布 authority branches、旧 rollout flags。
10. 文档/ADR、migration operator guide、监控与最终验收。

前两批是实施解阻条件；在 Runtime API 缺口关闭前，不应通过在 Studio 内循环调用 detail 或增加本地兼容层抢跑。

## 非长篇范围

short fiction、Play、interactive film、translation 的 chapter/file 模型是独立产品域。本 RC-1 既不修改它们，也不以长篇 Runtime authority 标准推断其 owner。只有已有独立 ADR 或后续明确决策，才能把这些模块接入同一 port。
