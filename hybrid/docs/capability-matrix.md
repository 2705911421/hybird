# 能力矩阵

决策词严格表示最终责任：`Keep InkOS`、`Keep webnovel-writer`、`Rewrite as adapter`、`Remove`、`Defer`。其中 “Keep webnovel-writer” 表示迁移可复用 Python 逻辑到 Story Runtime，并非原目录原样并存。

| 领域 | InkOS 实现 | webnovel-writer 实现 | 保留方案 | 淘汰方案 | 迁移风险 |
|---|---|---|---|---|---|
| 项目初始化 | Studio/CLI + Architect 生成书籍骨架、outline、truth 文件 | Deep init skill + `init_project.py` + Story contracts | **Keep InkOS** 交互；Runtime 提供 create/import command | 淘汰 Claude init skill 作为运行入口、淘汰双方直接写多份 canon | 高：初始化字段映射、用户确认语义 |
| 世界观 | Markdown outline/roles + structured runtime facts | `MASTER_SETTING.json`、state/index entities | **Keep webnovel-writer** 的结构化实体/规则模型，在 Runtime 重构 | InkOS 世界观 Markdown 不再是权威；旧 master JSON 变迁移输入 | 高：自由文本到结构化规则的信息损失 |
| 人物 | roles Markdown、current state facts、memory facts | entities/aliases/state_changes SQLite | **Keep webnovel-writer** SQL 模型并扩展 provenance/revision | InkOS roles/current_state 仅作视图；淘汰 state.json 人物副本 | 高：别名消歧和历史合并 |
| 关系 | character matrix Markdown/事实 | relationships + relationship_events | **Keep webnovel-writer** 时序关系事件模型 | 淘汰 character matrix 权威写入 | 中高：双向/多类型关系语义 |
| 时间线 | chapter summaries、current state、outline | story events、state_changes、chapter/volume contracts | **Keep webnovel-writer** event timeline | 淘汰 Markdown 时间线作为事实库 | 高：旧章缺少精确时间戳 |
| 伏笔 | hooks.json、hook lifecycle/arbiter/debt | open_loop/promise events、memory/debt | **Rewrite as adapter**：Runtime 建统一 `threads` 聚合，映射双方术语 | 淘汰双方并列 hook/open-loop 表 | 高：状态机和 payoff 语义不同 |
| 大纲 | InkOS Architect/Planner 与 story_frame/volume_map UX | chapter/volume contracts、fulfillment gate | **Keep InkOS** 生成与编辑；Runtime 持久化 outline execution | 淘汰文件直写和旧 contract 双写 | 高：计划版本与已执行状态并发 |
| 章节写作 | Planner → Composer → Writer，模型适配、长度治理 | webnovel-write skill 驱动宿主模型 | **Keep InkOS** | Remove Claude 写作 skill 运行时 | 中：保持 prompt 与 UI 体验 |
| 上下文检索 | governed composer、token budget、memory.db | ContextManager、精确 SQL、BM25/vector/RRF | **Rewrite as adapter**：InkOS Composer 调 Runtime query-context | 淘汰 InkOS memory.db 事实索引和 webnovel context 的 state.json 读取 | 高：质量回归、token 预算 |
| 审核 | ContinuityAuditor、33 维体系、Studio review | reviewer + review pipeline + schema | **Keep InkOS** 审核编排；Runtime 只校验事实/契约 | Remove Claude reviewer runtime；保留其 fixtures/规则作测试输入 | 中：审查维度映射 |
| 修订 | Reviser 多模式、保守自动修复 | skill 流程为主 | **Keep InkOS** | Remove webnovel 修订宿主流程 | 低中：修订后需重新 validate |
| 章节提交 | 多文件顺序落盘、state-degraded 恢复 | commit artifact、event/projection、write gates | **Keep webnovel-writer** 思想并重写事务服务 | Remove InkOS `persistChapterArtifacts` 作为权威提交；淘汰现有 JSON-first commit | 极高：核心切换点 |
| 事件系统 | interaction/play events；长篇没有统一 event store | StoryEvent、event log、projection router | **Keep webnovel-writer** schema/路由思想，在单 SQLite 重构 | 淘汰 JSON event authority 和 SQLite mirror 双写 | 高：事件版本、重放 |
| RAG | `memory.db` 关键词/相关性检索 | vectors.db、BM25、向量、RRF、rerank、backtrack | **Keep webnovel-writer** RAG 算法，作为可重建派生索引 | Remove InkOS 长篇 memory.db；精确事实禁止仅靠 RAG | 中高：外部 embedding、索引重建成本 |
| 导出 | TXT/MD/EPUB 与 Studio UX | contracts/snapshot/report | **Keep InkOS** 格式/交互；Runtime 提供一致性 snapshot | 淘汰读取散落 truth 文件的导出路径 | 中：大项目流式导出 |
| UI | Studio + TUI + CLI，完整创作交互 | 只读 Dashboard | **Keep InkOS** | Remove 独立 webnovel Dashboard；其诊断字段迁入 Studio 状态页 | 中：API DTO 适配 |
| 模型供应商 | 多 provider、per-agent routing、secret UI | embedding/rerank HTTP client | **Keep InkOS** 文本模型路由；Runtime 仅保留可插拔 embedding/rerank port | 淘汰 Python 对创作 LLM 的依赖 | 中：credential ownership |
| 配置 | inkos.json/.env/secrets/global env | env + Claude home + config dataclass | **Rewrite as adapter**：TS 产品配置、Runtime 专属 config、secret references | 淘汰 `~/.claude` 假设和跨层共享 env | 高：升级兼容、秘密迁移 |
| 恢复 | state-degraded、repair/resync、snapshots | run ledger、doctor、projection replay、backup | **Keep webnovel-writer** 恢复模型，在 Runtime 事务/checkpoint 化 | 淘汰依赖人工识别散落半状态 | 高：故障注入覆盖 |
| 数据迁移 | import chapters/canon，Markdown bootstrap | `migrate_state_to_sqlite.py`、backup/atomic replace | **Rewrite as adapter**：版本化、幂等 migration jobs | 淘汰启动时隐式 bootstrap 和一次性 destructive migration | 极高：可逆性与语义验证 |
| 测试 | 大量 Vitest、Windows/Ubuntu CI、LLM stubs | 83 个 pytest 文件，核心 CI 未运行 pytest | **Rewrite as adapter**：保留双方 fixtures，新增 contract/compat/fault tests | 淘汰依赖 Claude hook 的行为断言；live LLM 默认不跑 | 中高：跨语言一致性 |

## 结论

产品与创作智能由 InkOS 负责；长期状态、事件提交、精确查询、恢复和一致性由新的 Python Story Runtime 负责。交叉区域一律通过 adapter/API 收敛，不保留两套权威实现。

