# 重复能力与退出方案

## 决策总则

每组能力只有一个最终 owner。`Keep webnovel-writer` 指提取/修改可复用 Python 逻辑进入 Story Runtime；原 Claude 插件、原文件布局和双写行为不进入产品运行时。

| 重复能力 | 决策 | 最终 owner | 另一实现如何退出 | 验收信号 |
|---|---|---|---|---|
| 项目创建交互 | **Keep InkOS** | TypeScript Application | webnovel init skill 退为迁移参考/fixture；Python 只接收结构化 create command | Studio 创建书后 Runtime 返回 project revision |
| Canon/事实存储 | **Keep webnovel-writer** | Python Runtime SQLite | InkOS state JSON/Markdown 变只读 projection；webnovel state.json/contract JSON 变 import/export | 任一事实只有一条 authority row + provenance |
| 人物/别名 | **Keep webnovel-writer** | Runtime Entity service | InkOS roles 不再直接写；UI 编辑转 command | alias 查询和历史在 API 可追踪 |
| 关系与关系历史 | **Keep webnovel-writer** | Runtime Relationship projection | InkOS character matrix 由 Runtime 导出 | event replay 后关系投影 hash 一致 |
| Hook/伏笔/open loop | **Rewrite as adapter** | Runtime NarrativeThread service | hooks.json 与 memory open_loop 只作迁移输入，之后删除双写 | 单一状态机覆盖 create/advance/defer/resolve |
| 大纲生成 | **Keep InkOS** | Planner/Architect | webnovel plan skill 不再执行生成；Runtime 仅保存/校验 plan versions | Planner 输出 schema 通过后才能 persist |
| 大纲执行追踪 | **Keep webnovel-writer** | Runtime OutlineExecution projection | InkOS 文件中的“已执行”标记改为投影 | commit 自动推进节点且可 replay |
| 章节生成 | **Keep InkOS** | Writer pipeline | webnovel-write skill Remove | Python Runtime 不调用创作 LLM |
| 上下文组合 | **Rewrite as adapter** | TS Composer（编排）+ Runtime（数据选择） | InkOS 不再直接扫 truth/memory；webnovel 不再拼最终 prompt | trace 能分开 data selection 与 prompt assembly |
| 精确事实查询 | **Keep webnovel-writer** | Runtime Query service | InkOS memory lookup 退出长篇事实查询 | entity/relation/timeline 查询不依赖 embedding |
| 语义 RAG | **Keep webnovel-writer** | Runtime Retrieval service | InkOS memory.db 删除；vectors 只作派生索引 | 删库可从 authority 重建，结果带 source refs |
| 审核编排 | **Keep InkOS** | ContinuityAuditor/Studio review | webnovel reviewer agent Remove；其规则转确定性 validator/tests | UI 仍保留 InkOS review 流程 |
| 事实校验 | **Rewrite as adapter** | Runtime Validator | InkOS LLM StateValidator 只产建议，不再决定持久状态 | validator 输出结构化 violations + evidence |
| 修订 | **Keep InkOS** | Reviser | webnovel 相关 skill Remove | 修订后重新 prepare/validate，不直接落权威状态 |
| 章节持久化 | **Keep webnovel-writer** | Runtime Commit service（重构） | InkOS file persistence Remove；现 webnovel JSON-first 流程也 Remove | prepare→finalize 单事务，可安全重试 |
| 事件追加 | **Keep webnovel-writer** | Runtime Event store | InkOS 长篇无独立 event store；webnovel JSON event 文件退出 authority | `(project_id,event_id)` 唯一且 revision 连续 |
| 投影 | **Keep webnovel-writer** | Runtime Projection engine | InkOS Markdown projection writer 改 API consumer；原多个独立 DB/file writer 退出 | checkpoint、重放、hash verify |
| 快照/导出 | **Rewrite as adapter** | Runtime snapshot + InkOS formatter | Runtime 产一致 snapshot；InkOS 转 TXT/MD/EPUB | 导出绑定 revision 和 checksum |
| Dashboard | **Keep InkOS** | Studio | webnovel Dashboard Remove；健康/commit/replay 页面迁入 Studio | 无第二个用户 UI 服务 |
| CLI/TUI | **Keep InkOS** | TypeScript CLI/TUI | Python CLI 仅保留运维/内部，不面向普通创作用户 | 用户不需 Claude 或直接跑 Python 命令 |
| Doctor | **Keep webnovel-writer** | Runtime Doctor + TS façade | InkOS doctor 只检查产品/模型；合并显示但不复制检查逻辑 | 一次 Studio/CLI doctor 显示双层状态 |
| 运行日志/ledger | **Keep webnovel-writer** | Runtime Operations | InkOS daemon JSONL 限于应用日志，不表示提交事实 | 每 request/commit 可审计、可脱敏 |
| 模型配置 | **Keep InkOS** | TS Provider registry | Python 不读取创作模型 key；仅取 embedding secret reference | Runtime API 永不返回 secret |
| Claude hooks/skills | **Remove** | 无 | 行为约束转成 Runtime policy、API schema、tests | 脱离 Claude 后权限仍成立 |
| Play/互动影视/短篇 | **Defer** | InkOS 原模块 | Phase 0-8 不迁移到 Story Runtime，不影响长篇主链 | 长篇切换不回归这些既有能力 |

## 明确禁止的临时状态

- 禁止 TS 同时写 InkOS truth JSON 和 Runtime SQLite。
- 禁止 Runtime 同时把 commit JSON 与 SQLite 都标为权威。
- 禁止 Studio 查询 SQLite 表或 `.story-system` 文件。
- 禁止用同步脚本“最终一致”掩盖缺失的 revision/idempotency 语义。
- 禁止让 Agent 通过通用 write/edit 绕开 Runtime command。

