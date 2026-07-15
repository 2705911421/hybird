# RC-1D 最终章节读取架构

## 唯一产品边界

Studio、CLI、TUI、pipeline、agents、analytics 与 export 统一依赖 `ChapterApplicationService`。`ProjectChapterAuthorityResolver` 是唯一 authority selector：Runtime project 只返回 `StoryRuntimeChapterReadAdapter`，legacy project 只返回 `LegacyChapterReadAdapter`。

Runtime adapter 的 list/get/summary/search/export/analytics 均执行 Runtime health/version/schema/database handshake。surface 不按 mode 分支，也不在 typed error 后切换 adapter。

## Runtime 合同

| 能力 | Endpoint | 一致性 |
| --- | --- | --- |
| collection | `GET /api/story-runtime/v1/projects/{id}/chapters` | cursor 绑定 revision；跨页 revision 改变失败 |
| detail | `GET /api/story-runtime/v1/projects/{id}/chapters/{number}` | finalized body、checksum、commit/revision、timestamps |
| aggregate | `GET /api/story-runtime/v1/projects/{id}/chapter-aggregate` | count/latest/characters/chapter/volume 在一个读事务中 |
| search | `GET /api/story-runtime/v1/projects/{id}/chapter-search` | 只命中 finalized Runtime rows；result 绑定 revision |
| export | `POST /api/story-runtime/v1/projects/{id}/chapter-export` | 单一 SQLite read transaction；支持 expected revision |

## 产品行为

- Studio、CLI、TUI 的 collection/detail/stats 与 Runtime revision 一致。
- Runtime analytics 的已知基础指标来自 aggregate；Runtime 未提供的 audit 指标返回 `null`，UI/CLI 显示 `N/A`，不伪造 100%。
- Export formatter 只消费 `ChapterExportPort.exportSnapshot()`，不读 chapter Markdown。
- 删除或篡改 local projection 不改变 list/detail/search/analytics/export。
- Runtime unavailable 时读取、Studio `write-next` 与依赖 Runtime 的上下文均 fail closed。

## 已退休路径

- `shadow` 不再是正式配置或生产路径。
- `fallbackOnUnavailable` 已从配置 schema、bootstrap 与 CLI 写入路径移除；迁移器只删除遗留键。
- Runtime authority 的 local chapter list、analytics reader、export body reader、route-level authority branching 与 silent fallback 均不可达，并由 CI gate 阻止回归。

## 保留边界

Legacy adapter 与 migration/import scanner 保留，但只能读取明确 legacy/import source。非长篇模块不在 RC-1 owner 变更范围。详细规则见 `legacy-read-boundary.md`。
