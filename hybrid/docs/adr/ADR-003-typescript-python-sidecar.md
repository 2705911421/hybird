# ADR-003：采用 TypeScript + Python sidecar 边界

- 状态：Accepted
- 日期：2026-07-11

## 背景

InkOS 的核心优势集中在 TypeScript 产品和 Agent 编排；webnovel-writer 的结构化状态、SQLite、RAG、投影与恢复代码集中在 Python。

## 决策

TypeScript 负责 UI、模型调用、Agent、创作 workflow、prompt 与 Runtime client；Python sidecar 负责数据模型、SQLite、RAG、事件、投影、校验、提交、迁移和恢复。只通过 versioned JSON API 通信。

## 后果

- 两个语言栈可分别跟踪上游并独立测试。
- 本地 sidecar 生命周期、端口发现、健康检查和 Windows 打包成为产品责任。
- 禁止 TypeScript 直接读取 SQLite 表，禁止 Python 调用创作 LLM。

