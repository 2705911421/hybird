# ADR-001：选择 InkOS 作为产品外壳

- 状态：Accepted
- 日期：2026-07-11

## 背景

InkOS 已有 Studio、CLI、TUI、共享交互内核、模型路由、Planner/Composer/Writer/Auditor/Reviser 和人工 review。webnovel-writer Dashboard 只读，主要交互依赖 Claude Code skills。

## 决策

保留 InkOS 的 TypeScript 产品壳与创作编排。Story Runtime 仅以版本化 API 提供状态和一致性能力，不替代 Studio，也不运行创作 LLM。

## 后果

- 最大限度保持现有用户体验，并可分阶段接入。
- Studio 的 truth/章节直写路由必须逐步改为 Runtime client。
- webnovel Dashboard 最终删除，其诊断字段迁入 Studio。

