# RC-1 Legacy 读取边界

## 保留原因

`LegacyChapterReadAdapter` 未删除。它仍服务尚未 cutover 的 legacy 长篇，以及 migration/import 对旧 `index.json`、Markdown 的显式输入读取。删除它会破坏已识别的 legacy/importer 依赖，不满足 RC-1D 的删除前提。

## 可达边界

```text
authorityMode=legacy
  -> ProjectChapterAuthorityResolver
  -> LegacyChapterReadAdapter
  -> StateManager.loadChapterIndex() / chapters/*.md

migration/import command
  -> migration scanner/importer
  -> user-selected legacy source
  -> Runtime import contract
```

Runtime authority 路径为：

```text
authorityMode=runtime
  -> ProjectChapterAuthorityResolver
  -> StoryRuntimeChapterReadAdapter
  -> Runtime health/version/schema handshake
  -> Runtime product read API
```

两条路径不在错误处理、route、command 或 UI 层重新合并。resolver 只接受 `runtime` 与明确的 `legacy` project authority；`shadow`、未知 mode 和未知 authority 值直接失败。

## 禁止事项

- Runtime unavailable 后构造或调用 `LegacyChapterReadAdapter`。
- 用 local index/Markdown 补齐 Runtime collection、body、analytics 或 export。
- 用 local projection bootstrap、repair 或覆盖 Runtime。
- 把 importer scanner、migration source 或 final export 当作 current product read。
- 重新引入 `fallbackOnUnavailable` 或把 `shadow` 恢复为 production mode。

## 门禁

`inkos/scripts/check-runtime-chapter-authority.mjs` 解析 TypeScript AST、import edges、调用点和 Runtime adapter 内部方法可达关系，检查：

- Runtime roots 不调用 `loadChapterIndex()`、`getNextChapterNumber()` 或 `loadDurableStoryProgress()`；
- Runtime adapter 的 list/get/summary/export/search/analytics 都可达 compatibility handshake，且不可达本地 reader；
- exporter 只调用 `exportSnapshot()`，不导入文件系统正文 reader；
- Studio/CLI/TUI 的指定 surface 构造 `ChapterApplicationService`；
- resolver Runtime 分支不可达 legacy adapter；
- local projection 不反向 bootstrap；
- production AST 不包含 authority `shadow` 或 `fallbackOnUnavailable` 配置。

## 回滚约束

代码可通过 Git 回滚单个 consumer 或 adapter 修复，但 Runtime authority 不允许回滚为 local owner。若 Runtime adapter 回归，应停止发布并 fail closed；不得通过改 mode、启用 flag 或捕获异常后调用 legacy 来恢复服务。
