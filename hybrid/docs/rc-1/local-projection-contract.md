# RC-1B 本地章节 projection 合同

## 允许职责

Runtime authority 项目中的本地章节相关文件只允许属于以下类别：

| 类别 | 允许用途 | 是否 current authority |
|---|---|---|
| human-readable export | 用户明确导出的 TXT/MD/EPUB | 否 |
| disposable projection/cache | 可从 Runtime snapshot 重建的显示或分析材料 | 否 |
| backup artifact | 显式备份，带来源 revision | 否 |
| migration compatibility | cutover 前 legacy source/dry-run 输入 | 否 |

`chapters/index.json`、章节 Markdown 和 memory 不参与 authority mode 判断，不决定章节存在性、顺序、latest、正文、checksum、统计或 export collection。

## 必需元数据

新生成的 Runtime-backed export/projection 必须有 manifest，至少记录：

```json
{
  "authority": "runtime",
  "projectRevision": 7,
  "snapshotId": "project:7:...",
  "collectionChecksum": "sha256",
  "chapterCount": 3,
  "generatedAt": "RFC3339",
  "chapters": [{ "number": 1, "bodyChecksum": "sha256" }]
}
```

未携带 Runtime revision、snapshot ID 和 checksum 的既有 Markdown/index 一律标记为 unverified legacy artifact。它们可以用于迁移扫描，但不得声称为 current projection。

## 生命周期规则

1. Projection 只能从 Runtime finalized snapshot 单向生成。
2. 删除 projection 不影响 Studio/CLI/TUI 的 list/detail/analytics/search/export。
3. Runtime body/checksum 与 projection 不同，以 Runtime 为准；不得反向同步覆盖。
4. 正常启动不扫描本地 Markdown bootstrap Runtime，也不自动补写 Runtime。
5. Cache revision 与当前 Runtime revision 不同即 stale；不能作为当前事实返回。
6. Cutover 后 legacy source 保留也不改变 adapter 选择。

## 当前实现

产品读取不创建或依赖本地章节 projection。显式 export 写出正文文件和同路径 `.manifest.json` sidecar。旧本地章节仍可由 deprecated/import-only `LegacyChapterReadAdapter` 和 migration scanner 读取；architecture gate 阻止其进入 Runtime authority 生产路径。
