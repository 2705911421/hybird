# ADR-004：采用事件驱动章节提交

- 状态：Accepted
- 日期：2026-07-11

## 背景

InkOS 当前章节、truth、index、snapshot、memory 顺序写入；webnovel-writer 当前 commit JSON、event JSON/SQLite、多个 projection writer 也不是单事务。

## 决策

每章执行 `prepare → validate → stage body → persist chapter → append events → update core projections → verify → finalize`。从 persist 到 finalize 位于一个 SQLite transaction；派生索引通过 transactional outbox。

## 后果

- request/idempotency/project/revision 使提交可安全重试。
- 核心投影必须是纯确定性 reducer；外部副作用不能在事务内执行。
- 失败恢复依据 commit state/checkpoint，而不是猜测散落文件。

