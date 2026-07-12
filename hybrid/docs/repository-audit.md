# 仓库审计基线

## 1. 范围与方法

本报告以实际代码为准，不以 README 代替实现证据。审计基线：

- InkOS：`Narcooo/inkos@fd87b04c3fbac7ab6ebc1b022fa117ee8051825e`，仓库版本 `1.7.0`。
- webnovel-writer：`lingfengQAQ/webnovel-writer@59654ccaa17f240c5ae41fe51db9443284f8ca1f`，插件版本 `6.2.1`。
- 初始工作区只有根 `.git`，两个上游目录并不存在；本次按指定 URL 克隆到 `inkos/` 与 `webnovel-writer/`，新建产物仅位于 `hybrid/`。

审计覆盖目录、依赖、入口、Agent、workflow、模型、存储、上下文、章节写入、审核/修订、RAG、UI、测试、CI、配置、宿主耦合、安全与许可证。代码路径均相对于工作区根。

## 2. InkOS 代码事实

### 2.1 结构、依赖与入口

- pnpm monorepo：根 `package.json` + `pnpm-workspace.yaml`，包含 `packages/core`、`packages/cli`、`packages/studio`。
- Node `>=20`、pnpm `>=9`；core 使用 TypeScript、Zod、TypeBox、`@mariozechner/pi-*`；Studio 使用 React、Hono、Vite、Zustand；CLI 使用 Commander、Ink。
- CLI 入口为 `packages/cli/src/index.ts` / `program.ts`，命令位于 `packages/cli/src/commands/`。
- Studio server 入口为 `packages/studio/src/api/index.ts`，核心路由集中在约 6200 行的 `packages/studio/src/api/server.ts`。
- CI 在 Windows/Ubuntu、Node 20/22/24 上执行 install/build/test；发布流水线另有 canary、tarball 和安装 smoke test。

### 2.2 Agent 与创作 workflow

- 真实 Agent 类包括 Architect、Planner、Composer、Writer、StateValidator、ContinuityAuditor、Reviser、ChapterAnalyzer、Consolidator、FoundationReviewer，以及短篇/互动影视/Play 专用 Agent。
- `packages/core/src/pipeline/runner.ts` 是长篇主编排器；主要入口包括 `initBook`、`writeDraft`、`planChapter`、`composeChapter`、`auditDraft`、`reviseDraft`、`writeNextChapter`、`repairChapterState`、`resyncChapterArtifacts`、`importChapters`。
- Studio、TUI、CLI 与自然语言交互共享 core 层能力，但 Studio API 自己直接实例化/调用大量 core 服务，应用层边界较宽。
- `packages/core/src/agent/agent-tools.ts` 暴露 `write_truth_file`、章节文本 patch/replace、通用 read/edit/write 等工具；当前 Agent 工具仍具备直接修改持久文件的能力，不满足目标系统“Agent 不得直接写权威状态”的原则。

### 2.3 状态、上下文与 RAG

- `story/state/manifest.json`、`current_state.json`、`hooks.json`、`chapter_summaries.json` 由 Zod schema 校验；Markdown 是可读投影。
- `runtime-state-store.ts` 会在缺少结构化状态时从 Markdown bootstrap，然后并行写四个 JSON 文件。该兼容路径意味着旧 Markdown 仍能反向生成结构化状态，迁移期必须明确关闭条件。
- `memory-db.ts` 使用 Node 22+ `node:sqlite` 保存 facts/hooks/summaries；Node 20 会降级，CLI 明确提示退回 Markdown 路径。它是检索加速层，不是完整事实事务库。
- Composer 有受保护/可压缩上下文、token 预算、相关 outline section、最近章节尾句、hook debt 与 SQLite memory 检索；不是简单全量注入。
- 状态 JSON、Markdown 投影、快照与 `memory.db` 同时存在。设计意图有主从，但写入分散，异常时仍可能发生投影/索引漂移。

### 2.4 章节持久化、审核与恢复

- `persistChapterArtifacts()` 的顺序是保存章节 → 保存 truth files → 更新章节索引 → 更新书状态 → 写审计漂移指引 → 快照 → 同步 memory history。
- 上述操作跨多个文件/数据库且没有统一事务日志、prepare 记录、expected revision 或通用 idempotency key；任一步骤中断可能留下可见的部分结果。
- State validation 失败会仅重试 settlement；再次失败则保存正文并标记 `state-degraded`，保留旧状态供人工修复。这比静默损坏好，但不等价于原子章节提交。
- 审核与修订能力成熟：连续性审核、长度归一、关键问题保守修复、人工 review status 均已有实现，适合保留在 TypeScript 应用/编排层。

### 2.5 Studio、配置、安全与平台

- Studio 覆盖书籍、章节、truth editor、写作、审核、修订、导出、模型服务、分析、Play 等大量交互，产品壳明显强于另一项目。
- Studio 直接暴露 truth 文件 PUT 与章节文本 PUT；未来必须改为调用 Story Runtime command API，而不是写权威文件。
- 配置分布于 `inkos.json`、项目 `.env`、全局 `~/.inkos/.env`、`.inkos/secrets.json`；代码有 key masking 和 path traversal 测试，但 CLI 仍支持 literal `--api-key`，有 shell history 泄漏风险。
- Windows 已纳入 CI；Play SQLite 特别处理句柄关闭。Studio 启动时缺前端会同步执行 `npx vite build`，可能阻塞启动并引入运行期构建不确定性。

### 2.6 测试与许可证

- core、CLI、Studio 均有大量 Vitest；Studio 另有 Playwright 配置。测试广泛覆盖状态 reducer、投影、memory、composer、pipeline、恢复、安全与 UI store。
- 根及三个 npm package 均声明 `AGPL-3.0-only`。任何迁移代码必须保留版权和 AGPL 义务；网络服务形式尤其需要法律复核。

## 3. webnovel-writer 代码事实

### 3.1 结构、依赖与入口

- 仓库根是 marketplace；实际插件根为 `webnovel-writer/webnovel-writer/`。
- Python `>=3.10`，核心依赖 aiohttp、filelock、Pydantic；Dashboard 为 FastAPI + React/Vite；无标准 `pyproject.toml`，主要依赖 requirements 文件与脚本路径导入。
- 统一 CLI 为 `scripts/webnovel.py`，转发 `where/preflight/doctor/write-gate/projections/index/state/rag/context/migrate/chapter-commit/...`。
- 插件通过 `.claude-plugin/plugin.json`、skills、agents、hooks 交付；不是独立 daemon/API 服务。

### 3.2 Agent、skills 与 Claude Code 耦合

- Agent 文件为 `context-agent.md`、`data-agent.md`、`reviewer.md`、`deconstruction-agent.md`；它们依赖宿主按 prompt/allowed-tools 执行。
- 8 个 skills 大量使用 `CLAUDE_PLUGIN_ROOT`、`CLAUDE_PROJECT_DIR`、`AskUserQuestion`、`Agent`、Claude slash command 和 `PreToolUse/SessionStart` hook。
- `hooks/hooks.json` 只对 Claude 的 Write/Edit/MultiEdit/Bash 做 best-effort 写保护。脱离 Claude 后该权限边界自动消失，因此不能把 hook 当安全内核。
- Python CLI 本身多数可独立运行，是可复用的主要来源；skills/agents 应作为行为规范与测试样本，而不是 sidecar 的运行时依赖。

### 3.3 Story System、数据模型与权威性

- Pydantic 模型校验 review、fulfillment、disambiguation、extraction、StoryEvent；事件 ID 可由章节、序号与稳定 payload hash 生成。
- 真实存储是多层的：`.story-system/commits/*.commit.json`、`events/*.events.json`、`chapters/`、`volumes/`、`reviews/`，加 `.webnovel/state.json`、`index.db`、`vectors.db` 和 project memory 文件。
- `EventLogStore.write_events()` 先写 JSON 文件，再向 `index.db.story_events` 执行 `INSERT OR IGNORE`。SQLite 在此是 mirror；JSON 与 DB 任一失败都可能不同步。
- `StateManager` 仍维护精简 `state.json`，并 best-effort 同步 SQLStateManager；代码明确存在“state 已写但 SQLite 同步失败，需 projections retry”的状态。
- 因此当前代码并不满足“SQLite 为唯一权威源”。可复用的是 schema、事件归一、write gates、doctor、投影职责划分和迁移经验，不是现成持久层拓扑。

### 3.4 章节提交、投影与恢复

- `ChapterCommitService.build_commit()` 先验证四类 artifact，决定 accepted/rejected，并设置五类 projection 为 pending。
- CLI 顺序为 persist commit JSON → append events → 逐个执行 state/index/summary/memory/vector writer → 再 persist 带 projection status 的 commit。
- writer 异常被捕获并记录 `failed:*`，其余 writer 继续；这支持补偿，但不能保证章节、事件和全部投影处于一个 SQLite transaction。
- 事件 `event_id UNIQUE` + `INSERT OR IGNORE` 提供局部幂等；没有 request_id、project revision、chapter commit aggregate idempotency 或并发 compare-and-swap。
- `projections.py` 能从 commit 文件重放；run ledger、project phase、doctor 和 write gates 对中断恢复很有价值。

### 3.5 上下文、精确查询与 RAG

- ContextManager 从 state/index/summary/story contract 构造分层 context pack，含窗口、动态权重、deterministic ranker 与长期 memory orchestrator 选项。
- KnowledgeQuery/IndexManager 提供实体、状态变化、关系事件等精确查询；这些应优先于 RAG 回答事实问题。
- RAGAdapter 使用独立 `vectors.db`，支持 BM25、向量、RRF、rerank、parent backtrack 与降级模式；依赖外部 embedding/rerank API 时可退回 BM25。
- 上下文选择有 top-k/window，但未形成统一的、可度量的 token budget contract；百万字规模仍需明确硬预算和可观测 trace。

### 3.6 Dashboard、配置、安全与平台

- Dashboard 是只读 FastAPI/React 面板，直接读 `state.json`、`index.db`、`.story-system` 文件；UI 与内部 schema/路径强耦合。
- 配置从项目 `.env` 与 `~/.claude/webnovel-writer/.env` 读取，仍有 Claude home 假设；日志有敏感字段脱敏，Dashboard 仅报告 key 是否存在。
- `security_utils.atomic_write_json`、filelock、备份恢复和路径校验较完善；但大量同步文件 I/O 与许多短生命周期 SQLite connection 会限制高并发 sidecar。
- Windows UTF-8、路径、`os.replace`/WinError 5 重试已有专门兼容代码与测试，是值得迁移的实现经验。

### 3.7 测试、CI 与许可证

- 发现 83 个 Python test 文件，覆盖 commit schema/service、events、projections、SQL state、migration、doctor、write gates、RAG、上下文、Dashboard 与安全。
- GitHub Actions 目前只检查插件版本/发布元数据；没有在 CI 中运行完整 pytest、Dashboard frontend build 或跨平台矩阵。这是明显发布风险。
- 根与插件均为 GPLv3。与 InkOS AGPLv3 的组合通常可兼容于 AGPLv3 分发，但具体文件迁移、网络部署和第三方依赖仍需律师/维护者确认。

## 4. 主动识别的设计缺陷

| 缺陷 | 代码证据与影响 | 目标处置 |
|---|---|---|
| 同一事实多处存储 | InkOS JSON/Markdown/snapshot/memory.db；webnovel commit/events JSON + state.json + index.db + vectors.db | SQLite authority + transactional event store；Markdown/vector 仅投影 |
| Markdown/SQLite 不一致 | InkOS 可从 Markdown bootstrap；webnovel event file 先于 SQLite mirror | 迁移后禁止 Markdown 反向写入，除显式 import command |
| Agent 输出验证不足 | 两者都有 schema，但通用 write/edit 与自由文本链仍可绕过 domain command | Agent 只产出 proposal/artifact；Runtime schema + policy gate 决定写入 |
| 隐式共享状态 | 环境变量、当前项目指针、文件目录约定、单例式 runner 状态 | 每请求显式 project_id、revision、schema_version |
| 不受控 prompt 拼接 | 已有治理但来源繁多；外部材料与模型输出可进入上下文 | trust labels、长度上限、来源 trace、prompt-injection quarantine |
| 全量上下文风险 | webnovel 部分 core entities/legacy state 路径仍可能较大 | 精确查询优先，硬 token budget，按章节/实体/时间范围分页 |
| Agent 越权写状态 | InkOS truth editor/agent file tools；Claude hook 仅宿主内有效 | ADR-007 权限模型，只有 Runtime command handler 可写 |
| 非幂等整章提交 | 局部 event ID 幂等，但无 aggregate key/revision CAS | commit_requests + idempotency ledger + unique(project, key) |
| 投影半完成 | 两项目均跨多个持久化步骤；webnovel 显式保留 failed projection | 同 DB 事务内同步核心投影；异步派生投影 outbox + checkpoint |
| UI 与 schema 耦合 | 两个 Dashboard 都直读内部文件/表或 core shape | versioned API DTO；UI 不读 SQLite/文件 |
| Claude 专属耦合 | env、hooks、slash、Agent/AskUserQuestion | Python Runtime 纯 HTTP/stdio；宿主 adapter 独立 |
| Windows 文件锁 | node:sqlite/Play、atomic replace、db 文件句柄均有历史处理 | WAL、busy_timeout、短事务、显式 close、Windows CI fault tests |
| 大量同步 I/O | webnovel 大量 read_text/write_text/sqlite；InkOS 少量 sync build/play fallback | sidecar async API + worker pool；避免请求线程运行大扫描 |
| 无界日志/摘要 | JSONL、events、projection logs、chapter summaries 可持续增长 | retention/compaction policy、分区、checkpoint、可验证归档 |
| schema 版本不足 | 有局部 `story-system/v1`/Zod，但无统一跨语言兼容策略 | JSON Schema registry + compatibility tests |
| 无法重放副作用 | 通知、导出、外部模型/embedding 不能靠 DB replay 重做 | transactional outbox；replay 仅做纯投影，副作用带 delivery key |
| 测试依赖真实 LLM 风险 | InkOS 有 stub 测试；E2E/benchmark 与 provider 路径仍需隔离 | contract/fake provider 默认，live LLM 仅 opt-in |
| API key 泄漏 | literal CLI key、项目 secret files、第三方 base URL 转发 | OS/env secret reference，API 永不回显，日志统一 redact |
| Prompt Injection 污染状态 | 外部材料、章节正文、Agent extraction 可诱导持久化 | untrusted content 不得变成 command；事实须带 evidence + validator |

## 5. 已确认关键事实

1. InkOS 已有成熟产品壳与多 Agent 创作链，但其章节落盘不是跨文件/SQLite 的原子事务。
2. InkOS 的结构化 JSON 是当前长篇运行状态主源，`memory.db` 主要是检索加速；Node 20 仍可降级运行。
3. webnovel-writer 有更系统的 contracts、write gates、doctor、event/projection/replay 思想，但当前实现仍是多权威/多镜像混合形态。
4. webnovel-writer 的整章 commit 没有 request-level 幂等键和 expected revision；只有事件级稳定 ID/UNIQUE。
5. 两者 UI 都不能直接沿用为目标数据边界：InkOS Studio 的写 API 与 webnovel Dashboard 的读 API 都接触内部文件/结构。
6. 许可证分别是 AGPL-3.0-only 与 GPL-3.0；上游追踪和许可证保留是第一阶段阻断门。

## 6. 尚未确认的假设

- **H1**：最终 hybrid 项目整体可采用 AGPL-3.0-only。需项目所有者与法律审查确认。
- **H2**：Story Runtime 首版以本地单用户/单机为主，可使用单 SQLite writer；多用户远程服务延后。
- **H3**：章节正文文件可作为不可变/版本化 blob 由 Runtime 管理元数据，而正文内容不必全部存入 SQLite。需在 Phase 1 选型确认。
- **H4**：InkOS Studio 的现有 API 响应可通过 adapter 保持大部分兼容，不要求一次重做前端。
- **H5**：百万字目标的并发主要是“多个项目并行、单项目串行提交”，而非同一本书多作者同时提交。
- **H6**：embedding provider 允许离线/可替换实现；RAG 不应成为 commit 可用性的硬依赖。
- **H7**：上游仓库将以 Git subtree/patch provenance 或独立 remote 跟踪，具体 Git 策略尚未决定。

## 7. 高风险迁移点与最小改动建议

高风险依次为：旧 Truth/Markdown 到单一 SQLite 的语义映射；章节提交原子性与正文文件协调；事件 schema 稳定性；hook/伏笔和关系历史合并；AGPL/GPL 来源边界；Windows SQLite/文件锁；Prompt Injection 导致的错误事实固化。

第一批最小改动不迁移业务逻辑，只做：

1. 固定两个上游提交、许可证清单和 provenance 模板。
2. 在 `hybrid/contracts/` 冻结 v1 JSON 协议，并建立跨语言 schema fixture。
3. 新建空的 Python Story Runtime skeleton，只实现 health/status 和临时数据库 migration table（下一阶段才做）。
4. 在 InkOS 加一个只读 client seam，先 shadow-query，不替换现有 truth writer（下一阶段才改上游代码）。
5. 建立黄金项目 fixture、故障注入矩阵和基线性能指标。

