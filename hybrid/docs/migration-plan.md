# 分阶段迁移计划

原则：每阶段独立可运行、可测试、可回滚；旧 InkOS 主链在 Phase 4 完成前始终可用。所有文件名为建议目标路径，实际实施前需再核对上游最新提交。

## Phase 0：基线、测试和许可证审计

- **目标**：冻结上游提交、行为基线、golden fixtures、许可证/SBOM/provenance 格式。
- **修改文件**：`hybrid/docs/*`、`hybrid/UPSTREAM_PROVENANCE.yml`、`hybrid/tests/fixtures/*`、`hybrid/ci/baseline.*`；不改上游。
- **不修改范围**：InkOS runtime、Studio API、webnovel Python 业务行为。
- **风险**：现有测试依赖环境/网络；GPL/AGPL 解释不清。
- **测试**：双方原测试、build/typecheck、secret/license scan、Windows/Ubuntu 记录。
- **回滚**：删除 `hybrid/`；两个 clone 保持原提交。
- **完成定义**：基线结果可复现；每个拟迁移模块有来源/许可证；法律阻断项明确。

## Phase 1：Story Runtime 独立化

- **目标**：创建独立 Python package/service、SQLite schema、migration framework、health/status；尚不接 InkOS。
- **修改文件**：`hybrid/runtime/pyproject.toml`、`hybrid/runtime/src/story_runtime/{api,domain,db,migrations}.py`、`hybrid/contracts/*`、`hybrid/tests/runtime/*`。
- **不修改范围**：InkOS 写章和 truth；不复制 webnovel Dashboard/skills。
- **风险**：把旧 JSON mirror 误当权威；Windows SQLite lock；许可证污染。
- **测试**：schema migration up/down、WAL/busy timeout、idempotency ledger、revision CAS、crash injection、provenance check。
- **回滚**：停止 sidecar、删除试验 DB；无用户数据切换。
- **完成定义**：health/status/doctor 可运行；数据库从空库重复 migrate 结果一致；所有 write DTO 通过 contract tests。

## Phase 2：只读查询接入 InkOS

- **目标**：TS Runtime client 与 feature flag；Studio/CLI shadow 显示 Runtime status/entity query。
- **修改文件**：`hybrid/packages/story-runtime-client/*`，计划 patch `inkos/packages/core/src/story-runtime/*`、`inkos/packages/studio/src/api/*`、状态面板组件。
- **不修改范围**：InkOS 仍从原 truth 生成上下文和提交；Runtime 不写真实项目。
- **风险**：DTO 漂移、sidecar 启动失败、Windows 端口冲突。
- **测试**：OpenAPI generated/client fixtures、timeout/restart、旧 UI fallback、no-sidecar regression。
- **回滚**：关闭 `storyRuntime.readEnabled` feature flag。
- **完成定义**：只读查询 shadow 对比可观测；sidecar 不可用不影响旧写章。

## Phase 3：上下文组合器接入

- **目标**：Runtime 提供 authoritative facts + retrieval candidates；InkOS Composer 保留 prompt 组装。
- **修改文件**：Runtime `queries/context.py`、retrieval adapters；InkOS `agents/composer.ts`、`planner-context.ts`、trace schema；cross-language fixtures。
- **不修改范围**：章节持久化、审核/修订 UX；旧 truth 仍是提交主源。
- **风险**：上下文质量下降、token 超限、RAG 注入污染、entity alias 漏召回。
- **测试**：golden context diff、token hard limit、exact-query precedence、prompt-injection fixtures、百万字 synthetic benchmark。
- **回滚**：按 book/请求切回 legacy composer data source。
- **完成定义**：P95 上下文体积/延迟达标；权威事实冲突率为 0；trace 可解释选择来源。

## Phase 4：章节提交接入

- **目标**：Runtime 成为新项目章节/事实唯一写入者，完成事务提交和幂等重试。
- **修改文件**：Runtime commit/event/projection/outbox/artifact modules；InkOS `pipeline/runner.ts`、`chapter-persistence.ts`、StateManager adapter、Studio write endpoints。
- **不修改范围**：Writer/Auditor/Reviser prompt 和交互；Play/Short/Film 不切换。
- **风险**：最高；正文 blob 与 SQLite 协调、重复章节、response loss、revision conflict、Windows rename。
- **测试**：每个阶段故障注入、kill -9/restart、same-key retry、concurrent expected revision、projection hash/replay、large chapter blob。
- **回滚**：仅在 cutover 前用 dual-read shadow；cutover 后按项目 restore snapshot，不允许恢复双写。旧项目可保持 legacy mode。
- **完成定义**：新项目没有 InkOS truth authority 写入；所有提交可审计/重试；故障后 doctor 无未知半状态。

## Phase 5：审核和修订统一

- **目标**：InkOS 审核/修订产生 typed artifacts，Runtime 执行事实与契约校验；修订后重新 prepare/validate。
- **修改文件**：Runtime validation/review schemas；InkOS Auditor/Reviser adapter、Studio review routes/components。
- **不修改范围**：不把创作 LLM 移入 Python；不自动接受 blocking 修订。
- **风险**：旧 severity/维度语义不一致；LLM artifacts 弱格式。
- **测试**：malformed output、evidence spans、blocking gate、human approve/reject、audit retry。
- **回滚**：关闭 unified-review flag，保留 Runtime commit 但使用 legacy review UI mapping。
- **完成定义**：唯一 review artifact schema；Agent 无法绕过 validator；人工节点保留。

## Phase 6：Studio 状态面板接入

- **目标**：把 webnovel Dashboard 的 health/commit/event/projection/doctor 能力并入 Studio。
- **修改文件**：Runtime read DTO；InkOS Studio API client、status/health/timeline/recovery pages。
- **不修改范围**：不迁移 webnovel Dashboard 前端；Studio 不读表/文件。
- **风险**：大列表性能、schema 泄漏、敏感诊断信息。
- **测试**：pagination、redaction、large event timeline、sidecar degraded UX、access/path tests。
- **回滚**：隐藏新页面；Runtime/commit 不受影响。
- **完成定义**：普通用户无需第二 Dashboard/Claude；所有内部数据经 API DTO。

## Phase 7：旧 Truth 状态迁移

- **目标**：迁移 InkOS JSON/Markdown/memory.db 与 webnovel state/contracts/index 到单一 authority。
- **修改文件**：Runtime `migrations/import_inkos.py`、`import_webnovel.py`、mapping manifests、Studio migration wizard/report。
- **不修改范围**：源项目只读；不删除旧文件；不自动解决语义冲突。
- **风险**：最高；重复实体、伏笔状态机差异、章节编号/时间线冲突、编码、百万字耗时。
- **测试**：dry-run、mapping coverage、checksums、re-run idempotency、interrupt/resume、rollback snapshot、CJK/Windows paths。
- **回滚**：目标 DB restore/删除；源目录不变；migration job 保留 audit report。
- **完成定义**：事实/章节/关系/伏笔 coverage 达门槛；所有冲突已决策或显式 quarantine；源与快照 checksum 可验证。

## Phase 8：移除重复实现

- **目标**：关闭 legacy truth bootstrap、InkOS memory.db 长篇路径、webnovel Claude runtime/Dashboard 与 JSON authority。
- **修改文件**：InkOS state/memory/persistence compatibility code、Studio truth routes；hybrid packaging；deprecation docs。
- **不修改范围**：上游 clone 历史与版权；Play/Short 独立状态除非另立 ADR。
- **风险**：隐蔽调用者、旧插件用户、导出兼容。
- **测试**：dead-code/static import scan、no-direct-SQL/no-truth-write gates、legacy project migration smoke、full regression。
- **回滚**：发布前保留上一版本 binary 与迁移前 snapshot；不在同版本重新启用双写。
- **完成定义**：架构门禁证明只有 Runtime 写 authority；产品只有一个状态面板与一条长篇提交链。

## Phase 9：性能、稳定性和发布

- **目标**：百万字负载、长期运行、打包、升级、发布和上游同步流程达标。
- **修改文件**：benchmark、observability、installer/launcher、CI matrices、release/SBOM/provenance、运维手册。
- **不修改范围**：不在稳定期引入新领域模型或多数据库后端。
- **风险**：SQLite contention、索引增长、日志/快照无界、sidecar 生命周期、AGPL 发布义务。
- **测试**：100万字 synthetic corpus、10k events/replay、24h soak、Windows lock/restart、upgrade/downgrade、backup restore、offline mode、package install。
- **回滚**：版本化 DB backup + previous app/runtime bundle；schema downgrade 仅对声明可逆 migration。
- **完成定义**：SLO/容量阈值通过；发布包可一键启动；许可证/SBOM/源码提供满足要求；灾备演练通过。

## 跨阶段质量门

- 任何新增 write API 若缺五个元字段、schema 或 revision test，禁止合并。
- 任何 Runtime 数据被 Studio 直接从文件/SQLite 读取，禁止合并。
- 任何迁移来源缺 provenance/license，禁止合并。
- 任何测试默认调用真实 LLM/真实 embedding provider，禁止进入必跑 CI。
- 任何阶段引入双 authority，即使标注“临时”，也必须回退重新设计。

