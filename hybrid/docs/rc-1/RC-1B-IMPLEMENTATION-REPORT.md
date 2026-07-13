# RC-1B Implementation Report

日期：2026-07-13  
范围：Runtime authority 长篇项目 finalized chapter product reads

## 实施前声明

- 当前章节读 owner：Studio/CLI/TUI 多处由 `StateManager.loadChapterIndex()`、Markdown 和 memory 决定；detail 的部分路径已读 Runtime。
- 目标章节读 owner：`ChapterApplicationService` -> `ProjectChapterAuthorityResolver` -> `StoryRuntimeChapterReadAdapter`。
- 替代路径：Runtime authority 的本地 index/Markdown 枚举、目录 glob、local body、local analytics、exporter 文件扫描和 agent chapter grep。
- 保留 legacy：`LegacyChapterReadAdapter`、迁移 scanner/import、legacy-only 命令和 `StateManager.loadChapterIndex()` 本身。
- 保留 export/projection 文件：TXT/MD/EPUB formatter、显式 export 文件及 `.manifest.json`；本地章节 projection 仅为可删除 artifact。
- 新增 API：新增 Runtime collection、aggregate、export snapshot、product search API；新增 Core application ports/service。
- Schema：无 SQLite migration；新增/更新 OpenAPI、JSON Schema、Pydantic DTO、TypeScript/Zod DTO。
- 回滚：可回滚 consumer 代码或停止 rollout；Runtime authority 不回滚到 local owner，故障时 fail closed。
- 明确不做：RC-2、安全、sidecar、历史查询、真实用户数据迁移、short/Play/interactive film/translation owner 统一、formatter 重写。

## 完成内容

### Story Runtime

- 新增 `ChapterReadService`，提供 finalized collection、cursor/revision consistency、range/volume filter、aggregate、search 和单事务 export snapshot。
- detail/collection/export/search DTO 包含 chapter ID、title、body、summary、body/artifact checksum、commit、revision、timestamps、metadata。
- Runtime 对正文 checksum、revision cursor、expected export revision、finalized-only 和 malformed range 做 fail-closed 校验。
- 新增 endpoint：
  - `GET /api/story-runtime/v1/projects/{id}/chapters`
  - `GET /api/story-runtime/v1/projects/{id}/chapter-aggregate`
  - `POST /api/story-runtime/v1/projects/{id}/chapter-export`
  - `GET /api/story-runtime/v1/projects/{id}/chapter-search`

### InkOS Core

- 新增 `ChapterApplicationService`、`ChapterReadPort`、`ChapterExportPort`、`ChapterAnalyticsPort`、`ProjectChapterAuthorityResolver`、Runtime/Legacy adapters。
- Runtime adapter 验证每章 body checksum、多页 revision 和 typed Runtime errors；Runtime authority 不 fallback。
- exporter 改为只消费 `ChapterExportPort.exportSnapshot()`，保留 TXT/MD/EPUB formatter 并输出 manifest。
- pipeline、scheduler、book eval、project/shared actions、agent chapter search 和 Runtime review collection 改为使用 service。

### Studio / CLI / TUI

- Studio homepage/summary/list/detail/analytics/search/eval/detect/review/export/editor 读取统一经过 service；Runtime errors 映射为明确 unavailable/contract/version/locked 状态。
- CLI analytics/status/export/book count/detect/eval/review 与新增 `chapter list/show/latest/search` 使用 service。
- TUI 启动 summary/review reference 使用 Runtime service；Runtime 不可用时显示明确 system message。
- Runtime rewrite/resync/local-edit 路径在本地 projection 访问前 fail closed。

## 修改文件

RC-1B 相关修改/新增文件：

- Runtime：`hybrid/story-runtime/src/story_runtime/chapter_reads.py`、`contracts.py`、`api.py`、`tests/unit/test_chapter_reads.py`、`UPSTREAM_PROVENANCE.yml`。
- Contracts：`hybrid/contracts/story-runtime.openapi.yaml`、`contracts/schemas/chapter-artifact-response.json`、`chapter-collection-response.json`、`chapter-aggregate-response.json`、`chapter-export-request.json`、`chapter-export-response.json`、`chapter-search-response.json`。
- Core：`inkos/packages/core/src/chapter-application-service.ts`、Runtime client/schemas/index、pipeline/scheduler/book-eval/agent-tools、project-tools/edit-controller、export-artifact，以及 application-service/export/book-eval tests。
- CLI/TUI：`inkos/packages/cli/src/commands/analytics.ts`、`book.ts`、`chapter.ts`、`detect.ts`、`eval.ts`、`export.ts`、`review.ts`、`status.ts`、`write.ts`、`program.ts`、`tui/app.ts`。
- Studio：`inkos/packages/studio/src/api/server.ts`、`server.test.ts`。
- Gates：`inkos/scripts/check-runtime-chapter-authority.mjs`、`.github/workflows/rc1-chapter-authority.yml`、`inkos/package.json`。
- Docs：本目录的 architecture/projection/unavailable/export 文档及 `hybrid/docs/ADR-013-runtime-product-chapter-owner.md`。

工作树中另有 Phase 9/运营类 dirty files；它们不是本 RC-1B 交付的一部分，未被回滚或重新归因。

## 删除或禁止的生产路径

以下路径已从 Runtime authority 产品调用链移除或由 architecture gate 禁止：Studio route 直接调用 Runtime detail/local index、exporter `readdir/readFile` 章节正文、analytics `loadChapterIndex`、pipeline/scheduler 章节枚举、agent 对 `chapters/` 的递归 grep、Runtime 失败后的 legacy fallback。底层 Legacy adapter 和迁移输入路径未删除。

## API / schema 变化

- 新增 collection/aggregate/export/search Runtime read contracts；chapter artifact response 增加稳定 ID、volume 和时间字段。
- TypeScript/Zod、Pydantic、OpenAPI、JSON Schema 同步更新；contract test 校验 approved OpenAPI/schema。
- SQLite schema 无变化；没有真实项目自动迁移或 local Markdown 复制到 Runtime。

## 验证

通过：

- `python -m pytest -q`（Story Runtime 全量）
- `python -m pytest tests/unit/test_chapter_reads.py tests/contract/test_approved_contract.py -q`（10 passed）
- `pnpm typecheck`（Core、Studio、CLI）
- `pnpm --filter @actalk/inkos-studio test -- server.test.ts`（130 passed，含 Runtime revision-7/local conflict fixture）
- Core application-service、book-eval、export-artifact targeted tests
- `pnpm check:chapter-authority`（Runtime chapter authority gate passed）

## 已知问题

- Runtime analytics 当前提供 RC-1 要求的基础事实统计；文学 audit/quality 指标仍由可重建 projection 或既有 review 系统提供，不在本次 authority contract 中扩展。
- Legacy 项目仍依赖本地 index/Markdown，adapter 已标记 deprecated/import-only；未在本阶段删除迁移兼容代码。
- 旧 projection 若没有 revision/checksum manifest 只能标记为 unverified artifact，不能自动修补真实项目。

## 尚未完成或未执行

- `pnpm test` 及 Core/Studio 全量 Vitest 在本工作树 5/3 分钟上限内未结束；已终止超时的 Vitest 子进程，未将其计为全量通过。
- CLI 没有现成的 Vitest 测试目录；已完成 CLI typecheck，CLI/TUI 真实交互 parity 仍需独立 harness。
- Studio Playwright/browser E2E、真实运行中的 Runtime+Studio/CLI/TUI 跨进程 fixture、长时间 large-body soak 未执行。

RC-1B 到此停止，不进入 RC-2。
