# RC-1B Export 一致性

## 采用方案

采用 Runtime export snapshot DTO。InkOS exporter 继续负责 TXT、Markdown 和 EPUB 格式化，不直接访问 Runtime SQLite，也不读取本地章节 Markdown。

## Snapshot 流程

1. InkOS 通过 `ChapterExportPort.exportSnapshot()` 请求 finalized collection。
2. Runtime 在单一 SQLite 读事务中读取 project revision 和所有匹配的 FINALIZED chapters。
3. 若请求携带 `expected_revision` 且当前 revision 不同，Runtime 返回 `REVISION_CHANGED`，不产生 snapshot。
4. Runtime 按 chapter number 排序，逐章重新计算 body SHA-256 并与权威 metadata 比较。
5. Runtime 计算 `collection_sha256 = SHA256(number:body_sha256...)`，返回 snapshot ID、revision、章节正文和 timestamps。
6. InkOS adapter 再校验每章 body checksum，formatter 仅消费已验证 snapshot。
7. 文件 export 同时写 `.manifest.json`；Studio download 在 response headers 返回 revision、collection checksum 和 snapshot ID。

单事务 snapshot 的 `revision` 同时是 export start revision 和固定 snapshot revision。导出期间的新 commit 不会混入同一 snapshot；若调用方先固定 `expected_revision`，revision 变化会明确失败并要求重试。

## Manifest

Manifest 记录 authority、project revision、snapshot ID、collection checksum、chapter count、generatedAt 和每章 body checksum。章节顺序与 Runtime snapshot 数组完全一致。

## 失败条件

- Runtime unavailable/timeout/locked：export 失败。
- expected revision 不一致：export 失败并重试整个操作。
- 任一 body checksum 不一致：export 失败，不生成部分或混合文件。
- malformed/version mismatch：export 失败，不切换 local source。
- 空 collection：现有 formatter 行为保持为 `No chapters to export`。

## 格式范围

TXT、Markdown、EPUB formatter 保持原实现；RC-1B 只替换输入 port 并添加 manifest。approved-only 选项仍保留在 InkOS surface；Runtime 产品 read model 本阶段只公开 finalized chapters，不扩展 review/history 语义。
