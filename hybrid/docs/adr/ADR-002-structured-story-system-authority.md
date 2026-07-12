# ADR-002：选择结构化 Story System 作为权威状态源

- 状态：Accepted
- 日期：2026-07-11

## 背景

两个上游均存在 JSON/Markdown/SQLite/索引多层状态。webnovel-writer 提供更完整的实体、关系、事件、门禁、投影、doctor 和 replay 思想，但其当前实现仍有 JSON-first 与 SQLite mirror。

## 决策

新 Runtime 以 SQLite 中的规范表、append-only events、commit records 和 revision 为唯一权威。复用 webnovel-writer 的模型与算法时必须重构掉多主/双写。

## 后果

- 精确查询、恢复和审计有确定基线。
- 旧 Truth 必须通过显式、版本化、可回滚 migration 导入。
- vector、Markdown、Dashboard DTO 都是可重建投影。

