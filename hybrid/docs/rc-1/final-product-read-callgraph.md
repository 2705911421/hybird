# RC-1 最终产品读取调用图

## Runtime authority 主链

```text
Studio routes/components
CLI commands
TUI /chapters, /chapter <n>, /stats
pipeline / composer / continuity / agent tools
analytics / eval / review / export
              |
              v
ChapterApplicationService
              |
              v
ProjectChapterAuthorityResolver
              |
        authorityMode=runtime
              |
              v
StoryRuntimeChapterReadAdapter
              |
              +--> StoryRuntimeClient.assertCompatible()
              |      -> GET /api/story-runtime/v1/health
              |      -> runtime version + schema + ready DB
              |
              +--> collection/detail/aggregate/search/export snapshot
                     -> Runtime finalized rows at one declared revision
```

Runtime adapter 的每个产品操作都先到达 compatibility handshake。失败映射为 typed application error，调用链终止；没有通向 Legacy adapter、local index、chapter Markdown 或 analytics cache 的错误分支。

## Surface 到 service

| Surface | 产品入口 | Service 操作 | Runtime 能力 |
| --- | --- | --- | --- |
| Studio | book summary/list/detail、analytics、search、eval/review、export | `summary/list/get/analytics/search/exportSnapshot` | aggregate/collection/detail/search/export |
| CLI | book/status、chapter list/show/latest/search、analytics/eval/review/export | 同上 | 同上 |
| TUI | `/chapters`、`/chapter <n>`、`/stats` | `list/get/analytics` | collection/detail/aggregate |
| Pipeline | next chapter planning/composition | `summary/get` 与 Runtime context provider | aggregate/detail/context query |
| Agents | composer、continuity、context transform、chapter search | application service/Runtime context；本地 truth projection guard | detail/search/context query |
| Export | TXT/MD/EPUB formatter | `ChapterExportPort.exportSnapshot` | revision-bound export snapshot |

Studio/CLI/TUI 不检查 `storyRuntime.mode` 来选择 reader，也不直接 new legacy adapter。项目 authority 只在 resolver 边界解析一次。

## Error call graph

```text
Runtime stopped / timeout / locked / malformed / version mismatch / 401
  -> StoryRuntimeClientError
  -> ChapterApplicationError
  -> Studio typed HTTP / CLI non-zero / TUI system error
  -> STOP
```

401/403 映射为不可重试 `runtime_unauthorized`。stopped/timeout/locked 可按 typed policy 重试当前 Runtime 操作，但不能切换 owner。

## Legacy 与 importer

```text
authorityMode=legacy -> resolver -> LegacyChapterReadAdapter -> local index/Markdown
explicit migration/import -> scanner -> selected legacy source -> Runtime import
```

这是单独边界，不是 Runtime 主链的 fallback。local projection、final export、backup、search/analytics cache 都没有反向箭头指向 Runtime owner。
