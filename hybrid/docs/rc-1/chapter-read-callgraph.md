# RC-1D 当前章节读取调用图

本文已在 RC-1D 更新为实际生产代码。RC-1A 的迁移前分裂调用链保留在 `RC-1A-AUDIT-REPORT.md` 和 `local-chapter-source-inventory.md`，不再代表当前设计。

```text
Studio / CLI / TUI / pipeline / agents / analytics / export
                         |
                         v
              ChapterApplicationService
                         |
                         v
           ProjectChapterAuthorityResolver
             /                         \
 authorityMode=runtime            authorityMode=legacy
           |                            |
StoryRuntimeChapterReadAdapter   LegacyChapterReadAdapter
           |                            |
health/version/schema + API      local index/Markdown
           |                            |
Runtime finalized revision       pre-cutover/import-only
```

## Runtime product operations

| Operation | Application method | Runtime endpoint/data | Local authority reachable |
| --- | --- | --- | --- |
| list | `list()` / `listAll()` | finalized collection + revision cursor | no |
| detail | `get()` | finalized artifact + body checksum | no |
| summary | `summary()` | chapter/volume aggregate + timestamps | no |
| analytics | `analytics()` | Runtime aggregate；未知 audit 指标为 `null` | no |
| search | `search()` | Runtime finalized search result + checksum | no |
| export | `exportSnapshot()` | one Runtime revision snapshot | no |

每个 Runtime adapter 操作可达 `StoryRuntimeClient.assertCompatible()`。Runtime unavailable、timeout、locked、contract/version mismatch、checksum mismatch、revision changed、not found 和 unauthorized 都在 application boundary 映射；任何错误都不会重选 adapter。

## 写作与上下文

- Pipeline 的 next chapter number 来自 `ChapterApplicationService.summary()`，不再调用 local `getNextChapterNumber()`。
- Composer/continuity 通过 Runtime context/detail；Runtime authority 的 context transform 在读取本地 truth/story 文件前返回。
- Agent chapter search 通过 application service；Runtime authority 的 local story projection reader被阻止。
- Studio `write-next` 在接受异步写入前先执行 Runtime summary/handshake，失败即返回 typed error。

## 投影方向

```text
Runtime revision -> explicit export/cache/projection
local artifact -X-> Runtime bootstrap
local artifact -X-> product current result
```

`shadow` 和 `fallbackOnUnavailable` 已退出 production configuration。未知 mode/authority 值 fail closed。
