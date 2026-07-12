# ADR-008：许可证和上游代码追踪策略

- 状态：Accepted，法律结论待确认
- 日期：2026-07-11

## 背景

InkOS 为 AGPL-3.0-only，webnovel-writer 为 GPL-3.0。目标需要持续跟踪两个上游，同时保留版权、来源和修改原因。

## 决策

每个迁移文件记录 `source_repo`、`source_commit`、`source_path`、`license`、`modification_summary`；保留原版权头。建立 `UPSTREAM_PROVENANCE.yml` 和许可证扫描门禁。整体分发许可证暂定 AGPL-3.0-only，须在迁移代码前由法律/维护者确认。

## 后果

- Phase 0 未通过许可证兼容审查前不得复制业务实现。
- 上游同步使用可审查 patch，不做无来源的大块复制。
- 对第三方依赖、模型 SDK、前端资产也维护 SBOM 和 notice。

