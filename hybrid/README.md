# Hybrid Workspace Design Package

本目录包含审计与架构资料，以及已实施的 Story Runtime Phase 1 和 InkOS 只读接入 Phase 2/3。章节持久化仍由 InkOS 负责，Phase 4 尚未开始。

## 文档索引

- [仓库审计](docs/repository-audit.md)
- [能力矩阵](docs/capability-matrix.md)
- [重复能力与退出方案](docs/overlap-analysis.md)
- [目标架构](docs/target-architecture.md)
- [迁移计划](docs/migration-plan.md)
- [测试基线](docs/baseline-tests.md)
- [Phase 2/3 实施与配置](docs/phase-2-3-implementation.md)
- [ADR 目录](docs/adr/)
- [Story Runtime OpenAPI](contracts/story-runtime.openapi.yaml)
- [JSON Schemas](contracts/schemas/)

## 当前结论

推荐采用 InkOS TypeScript 产品壳 + Python Story Runtime sidecar。SQLite 是唯一权威状态源；Markdown、vector、Dashboard DTO 和导出均为输入或投影。当前 webnovel-writer 实现不应原样作为 sidecar，其 contracts、事件、write gates、doctor、projection/replay 和 Windows 恢复代码应经 provenance 记录后分阶段提取重构。
