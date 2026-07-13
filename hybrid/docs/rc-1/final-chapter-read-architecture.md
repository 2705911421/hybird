# RC-1B 最终章节读取架构

## 唯一调用链

```text
Studio / CLI / TUI / pipeline / scheduler / analytics / search / export
                              |
                    ChapterApplicationService
                    /          |            \
            ChapterReadPort ChapterAnalyticsPort ChapterExportPort
                              |
               ProjectChapterAuthorityResolver
                  /                         \
StoryRuntimeChapterReadAdapter       LegacyChapterReadAdapter
 authorityMode=runtime only          authorityMode=legacy only
                  |                         |
 Story Runtime product read API      index.json + Markdown
 Runtime SQLite authority            deprecated/import-only
```

Surface 不决定 authority，不捕获 Runtime error 后重选 adapter。Runtime authority 缺少 Runtime adapter 时 resolver 抛出 `runtime_unavailable`。

## Runtime 产品读取合同

| 能力 | Endpoint | 一致性 |
|---|---|---|
| collection | `GET /api/story-runtime/v1/projects/{project_id}/chapters` | cursor 编码 revision；后续页 revision 改变返回 `REVISION_CHANGED` |
| detail | `GET /api/story-runtime/v1/projects/{project_id}/chapters/{chapter_number}` | 返回稳定 chapter ID、正文、checksum、commit/revision、时间戳 |
| aggregate | `GET /api/story-runtime/v1/projects/{project_id}/chapter-aggregate` | 同一读事务得到 count/latest/characters/chapter/volume aggregates |
| export | `POST /api/story-runtime/v1/projects/{project_id}/chapter-export` | 单一 SQLite 读事务形成 snapshot；可要求 `expected_revision` |
| search | `GET /api/story-runtime/v1/projects/{project_id}/chapter-search` | 只命中 FINALIZED Runtime rows；正文/checksum 来自 Runtime；cursor 绑定 revision |

所有 collection/export/search 均按 Runtime `chapter_number ASC` 排序，只公开 finalized chapters。`finalized_only=false` 被拒绝。

## InkOS application service 职责

- 将 Pydantic/OpenAPI DTO 经 Zod 校验后映射为统一 TypeScript model。
- 校验 detail、search 和 export 中每章正文的 SHA-256。
- 在多页读取中验证 `projectRevision` 不变。
- 映射 unavailable、timeout、malformed contract、version mismatch、database locked、revision changed、checksum mismatch 和 not found。
- 为 Runtime analytics 提供 revision-bound 的 count、characters、latest、size、timestamps、volume 基础统计。
- 为 export formatter 提供 snapshot，而不是文件路径。

## Surface 收敛

- Studio：homepage/book summary、chapter list/detail、editor load、analytics、search、audit/detect body、eval、export 和 recent chapter 通过 service。
- CLI：`chapter list/show/latest/search`、status/stats/analytics/export/detect/eval/book count 和 Runtime review collection 通过 service。
- TUI：启动章节 browser summary 和 review chapter reference 使用同一 service；unavailable 作为明确 system message。
- Core：pipeline、scheduler、book eval、project actions、agent chapter search 和 exporter 使用 ports。

## 保留边界

`StateManager.loadChapterIndex()` 仍为 Legacy adapter、import/migration 和 legacy-only 写命令服务。Runtime authority 生产调用点由 CI architecture gate 禁止。Runtime 写/重写/本地编辑命令在接触本地 projection 前 fail closed。
