# ADR-013: Runtime 是产品级 finalized chapter owner

- 状态：Accepted
- 日期：2026-07-13
- 范围：Runtime authority 长篇项目

## 背景

RC-1A 证实写入由 Story Runtime 决定，但 Studio、CLI、TUI、analytics、search 和 export 的多数读取仍由 InkOS 本地 `index.json`、Markdown 或 memory 决定，形成双产品事实源。Runtime 已有权威写模型和单章读取，但缺少产品级 collection、aggregate、search 与一致性 export 合同。

## 决策

Story Runtime 是 Runtime authority 长篇项目 finalized chapters 的唯一产品 owner。章节存在性、顺序、latest、标题、正文、正文 checksum、summary、commit/finalized revision、时间戳、章节数、统计基础和 export collection 都由 Runtime 决定。

InkOS Core 的 `ChapterApplicationService` 是产品 surface 的唯一入口。`ProjectChapterAuthorityResolver` 集中选择：

- `authorityMode=runtime` 只选择 `StoryRuntimeChapterReadAdapter`；Runtime 缺失、超时、锁定、版本不匹配或 DTO 非法时 fail closed。
- `authorityMode=legacy` 可选择 deprecated/import-only 的 `LegacyChapterReadAdapter`。
- migrated 项目 cutover 后不得静默回到 legacy。

Runtime export 采用单事务 export snapshot DTO。Exporter 只格式化 DTO，不访问 SQLite，也不读取本地章节正文。

## 本地文件职责

本地 Markdown、`index.json`、memory 和 analytics 文件只能是 legacy import source、可删除 projection、带 manifest 的人类可读 export、backup artifact 或 migration compatibility。未带 Runtime revision/checksum 的旧文件视为 unverified legacy artifact，不能显示为 current，也不能反向覆盖 Runtime。

Runtime authority 正常启动不得从本地章节自动 bootstrap。删除所有本地章节文件不得改变 list/detail/analytics/search/export 结果。

## 后果

- 产品读取在 Runtime 不可用时会显式 unavailable，而不是展示看似正常的本地结果。
- Legacy 项目继续可读旧 index/Markdown，但生命周期为 deprecated/import-only。
- Runtime API 和跨语言 DTO 增加；数据库 schema 不变，无真实用户数据迁移。
- 现有 TXT/Markdown/EPUB formatter 保留，只更换数据来源并增加 export manifest。

## 回滚

可回滚 consumer rollout 或 additive API 代码，但不得让 Runtime authority 项目回到本地 owner。发生缺陷时停止 rollout、恢复上一版 Runtime-backed adapter 或 fail closed。

## 不在本 ADR 范围

RC-2、安全、sidecar、历史查询、真实数据迁移、short fiction、Play、interactive film、translation 与 formatter 重写。
