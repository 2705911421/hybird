# RC-1A Story Runtime 读取能力缺口

## 当前可复用能力

| 能力 | 当前 API / service | 结果 |
|---|---|---|
| project revision / latest chapter / authority | `GET /projects/{id}/status` | 已有；返回 `revision`, `latest_chapter`, `authority_mode` |
| chapter detail | `GET /projects/{id}/chapters/{chapter_number}` | 已有；只返回 `FINALIZED` 章 |
| chapter number/title/body | `ChapterArtifactResult` | 已有 |
| body checksum / artifact checksum | `body_sha256`, `artifact_sha256` | 已有 |
| chapter summary | `summary` | 已有 |
| chapter revision / commit identity | `revision`, `commit_id` | 已有 |
| finalized time | `finalized_at` | 已有 |
| deleted/aborted filtering | SQL `c.state='FINALIZED'` | 单章 detail 正确排除非 finalized commit；当前没有公开 deleted 状态模型 |
| commit history pagination | `GET /projects/{id}/commits?cursor&limit...` | 已有 cursor pagination，limit 1..100 |
| event timeline pagination | `GET /projects/{id}/events?cursor&limit...` | 已有 cursor pagination |
| generation context retrieval | `POST /queries/context` | 已有，用于 governed context，不是产品 search |
| projection/search index health | overview/projections | 已有运维可见性 |

权威单章 SQL 位于 `chapter_commits.py:116-128`：`chapter_commits` join `chapter_artifacts`，限定 `state='FINALIZED'`。DTO 与 `inkos/packages/core/src/story-runtime/schemas.ts` 的 Zod schema 在字段名和可空性上匹配，未发现当前单章 DTO 的 Python/TypeScript 漂移。

## 缺失或不适合复用的能力

| 要求 | 状态 | 缺口 / 不能替代的原因 | 阻塞范围 |
|---|---|---|---|
| chapter list | 缺失 | 没有 finalized chapter collection endpoint | 所有 list/recent/summary |
| list cursor pagination | 缺失 | commit pagination 不是 chapter pagination | 大型项目列表 |
| authoritative chapter count | 缺失 | status 只有 `latest_chapter`；不能由其推断无缺口 collection/count | dashboard/analytics |
| chapter metadata without body | 缺失 | 单章 DTO 总带完整正文 | list/recent 会形成巨大 payload |
| explicit ordering DTO | 缺失 | 没有稳定 `order_key`/volume/range semantics | list/export |
| latest chapter detail | 部分 | 可先 status 再单章，但有两次读取间 revision race | recent/latest detail |
| list by volume | 缺失 | schema 当前无公开 volume association | volume UI/export |
| list by range | 缺失 | 只能逐章 N 次请求 | export/eval |
| batch body read / export stream | 缺失 | 无 snapshot-consistent bulk read | txt/md/epub export |
| analytics aggregate | 缺失 | 没有 authoritative word count/status/summary aggregate | Studio/CLI stats |
| product search | 缺失 | `/queries/context` 面向生成层、无用户搜索 pagination/稳定命中 DTO | Studio/CLI/TUI search |
| deleted/aborted list filtering contract | 缺失 | 单章隐式只选 FINALIZED，但 list API 不存在，也没有 include/exclude contract | list/history correctness |
| application-level read model | 缺失 | Studio 只能拼 status/detail/commits 等底层 endpoint | 所有 surface 一致性 |

## 为什么现有 endpoint 不能拼成章节列表

- `latest_chapter` 是序列头，不是 collection count；未来删除、隐藏、重写或 migration gap 都会让二者不同。
- commits 包含 `VALIDATED`、`ABORTED`、`RECOVERY_REQUIRED`、`FINALIZED` 等状态，同一章也可能有多次尝试。
- `CommitSummary` 没有 title、summary、word count、body checksum 之外的完整章节 metadata；其目标是运维历史。
- events 是事实变更时间线，不是 finalized body collection。
- `/queries/context` 会按生成上下文预算选择内容，结果不是稳定、可分页、可完整导出的用户搜索合同。
- 逐章调用 detail 会产生 N+1、巨量正文 payload，并且跨请求不能保证同一 revision snapshot。

## DTO、payload 与版本问题

| 问题 | 观察 |
|---|---|
| 单章 DTO 一致性 | 当前 Python `ChapterArtifactResult` 与 TypeScript schema 一致 |
| 列表 DTO | 不存在，因而无法对齐 |
| 巨大正文 | detail 总返回 body；不能直接用于 metadata list |
| pagination | commits/events 有；章节没有 |
| version gate | `StoryRuntimeClient` 做 Zod DTO 校验，但不比较 `health.runtime_version` |
| process handshake | dirty `process-manager.ts` 比较 runtime/schema version，但只覆盖由 manager 启动的 Runtime |
| malformed DTO | client 能识别 schema mismatch；Studio chapter detail broad catch 把它抹成 404 |
| API 暴露内部表 | commits/events/projections 是有意运维 read model；若 Studio 用它们拼章节列表，会把内部 commit 状态泄露为产品语义 |

## 推荐 Runtime application-level read model

需要 Runtime 提供面向产品的读取合同，而不是让 Studio/CLI 拼接底层 endpoint。最小建议：

```text
GET /api/story-runtime/v1/projects/{project_id}/chapters
  ?cursor=&limit=&from_chapter=&to_chapter=&volume_id=
  -> { project_id, revision, total_count, latest_chapter, items[], page }

ChapterListItem:
  chapter_number, order_key, title, summary, body_sha256,
  artifact_sha256, resulting_revision, commit_id, finalized_at,
  word_count, volume_id?, state="FINALIZED"

GET /projects/{project_id}/chapters/{number}
  -> 现有 detail，可增加明确 ETag/revision 语义

POST /projects/{project_id}/chapter-export
  -> 固定 revision 的 range/batch/stream，返回正文与 metadata

GET /projects/{project_id}/chapter-analytics
  -> 固定 revision 的 authoritative aggregates

GET /projects/{project_id}/chapter-search?q=&cursor=&limit=
  -> 稳定 product search DTO，明确 index revision/stale 状态
```

list response 必须在同一 Runtime read transaction/snapshot 下返回 `revision`、`total_count`、`latest_chapter` 和 items；不能由 InkOS 客户端把多个请求的结果拼成假一致快照。

## Runtime unavailable / degraded 合同要求

Runtime adapter 对 stopped、timeout、DB locked、migration required、version mismatch、malformed DTO 必须返回可区分的 typed error。Runtime authority selector 不得捕获后改用 `LegacyChapterReadAdapter`。

若未来允许 cache，只能满足全部条件：

1. cache 带 `project_id`, `revision`, `body_sha256`/manifest checksum；
2. 明确显示 stale/offline 状态与 cache revision；
3. 只读；禁止 commit、export 为“当前版本”或无提示搜索；
4. cache 缺失或校验失败时明确失败；
5. 恢复 Runtime 后按 revision/checksum 重新验证。

## 阻塞判断

Runtime 已具备权威写入和单章 detail，不需要 fundamental ownership redesign；但 chapter collection、分页、批量正文、analytics 和 product search 是统一读取实施的硬缺口。仅在 InkOS 侧改 route 会导致 N+1、非快照一致和继续拼底层 endpoint。

因此结论为：

```text
IMPLEMENTATION BLOCKED BY RUNTIME API GAPS
```
