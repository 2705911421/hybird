# 最终架构审计

## 总结

状态：`FAIL`。Python authority/commit 内核是真实实现，不是空 HTTP 壳；但产品的章节列表、analytics、export 仍以 InkOS 本地 index/Markdown 为事实，形成两个对用户输出有决定权的数据路径。生命周期和产品读取面尚未统一。

## 产品层与状态层

| 检查 | 状态 | 证据与判断 |
|---|---|---|
| TS 负责 UI、Agent、模型与编排 | PASS | `pipeline/runner.ts`、Studio、CLI/TUI；Python 无创作 LLM import |
| Python 负责 SQLite、事件、投影、提交、恢复、迁移 | PASS | `chapter_commits.py`、`repository.py`、`observability.py`、`migration_jobs.py` |
| InkOS 不直接执行 Runtime SQL | PASS | `python hybrid/scripts/check_architecture.py`：10 rules passed |
| Studio 不直接打开 Runtime DB | PASS | Studio 通过 `StoryRuntimeClient`/proxy；静态门禁通过 |
| 仅通过版本化 API 通信 | PARTIAL | Runtime 通信使用 `story-runtime/v1`；但 Studio 同时读取 InkOS chapter index/Markdown |
| Python 不调用创作 LLM | PASS | contract gate 和生产 import 搜索无 OpenAI/Anthropic/InkOS |
| domain schema 只有一份 | PARTIAL | Python Pydantic、JSON Schema、TS Zod 三份需要 contract test 保持；`StoryRuntimeModeSchema` 仍接受 `shadow`，CLI 又拒绝该值 |
| 生命周期统一 | FAIL | `StoryRuntimeProcessManager` 仅导出和测试使用，生产无实例化 |

## 实际章节写入调用图

```mermaid
flowchart LR
  A["Studio / CLI / TUI / Agent"] --> B["PipelineRunner._writeNextChapterLocked"]
  B --> C["StoryRuntimeChapterPersistence.persist"]
  C --> D["Review validate"]
  D --> E["Runtime prepare"]
  E --> F["Runtime validate"]
  F --> G["Runtime commit transaction"]
  G --> H["SQLite chapter body + events + core projections"]
  H -. "未同步" .-> I["InkOS chapters/index.json + Markdown"]
  I --> J["Studio list / analytics / export"]
```

写入主链证据：`runner.ts:875,1230`、`chapter-persistence-port.ts:51`。读取断裂证据：`studio/server.ts:2816,3107`、`export-artifact.ts:68-118`。

## 单一权威介质矩阵

| 介质 | 声明角色 | 实际角色 | 状态 |
|---|---|---|---|
| Runtime SQLite | authority | facts、chapters、events、revision authority | PASS |
| Runtime story events | authority journal | commit 内 append；operator API 可直 append | PARTIAL |
| Runtime projections/FTS | projection/cache | 可 replay；不会覆盖 facts | PASS |
| Runtime snapshot | backup | checksum 验证的 SQLite backup | PASS |
| chapter Markdown/index | legacy/export | Studio 列表、analytics、export 的实际来源 | FAIL |
| `story/state/*.json` | legacy import/source | Runtime book 正常写入不使用；旧 InkOS 仍保留 | PARTIAL |
| `memory.db` | legacy evidence/cache | importer 标记 candidate evidence；旧 InkOS 模块仍存在 | PARTIAL |
| migration CIR | temporary/versioned import | import staging/provenance | PASS |
| event/commit JSON | API DTO/export | 非独立 authority | PASS |
| Studio local/session state | UI/session | 不应是 story authority | PASS |

真实 Chromium 证明同一项目首页显示 `0 chapters`，Runtime 页面显示 `revision 7/latest chapter 3`。截图：`output/playwright/final-audit/studio-home-zero-chapters.png` 与 `runtime-overview-revision-7.png`。

## 单一提交链

状态：`PARTIAL`。

- Runtime authority 自动写章进入同一 prepare/validate/commit service：PASS。
- direct chapter PUT 明确返回 `LEGACY_LONG_FORM_READ_ONLY`：PASS（`server.ts:2966`）。
- Markdown bootstrap 在 Runtime 路径抛错：PASS（`state/manager.ts:421`）。
- Runtime 不可用时 fail closed：PASS（`runner.ts:878-895,1998`）。
- `/events/append` 和 `/commands/typed-diff` 是第二类写入口；前者要求 operator scope，后者用于 typed domain command：PARTIAL。
- `executeEditTransaction` 仍从 core index 导出但未发现生产调用者：PARTIAL（deprecated/dead exported surface）。
- 产品 export/list 仍绕开 Runtime chapter store：FAIL。

## 红线

触发发布红线 1、17、20：章节的产品级读取/导出存在第二实际事实源；E2E 用户视图不一致；设计边界与真实产品调用路径严重不一致。

