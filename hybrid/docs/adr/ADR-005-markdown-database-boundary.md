# ADR-005：Markdown 与数据库职责边界

- 状态：Accepted
- 日期：2026-07-11

## 背景

Markdown 对作者友好，但两套系统历史上均存在从 Markdown 读取或 bootstrap 状态的路径，容易形成第二权威源。

## 决策

Markdown 只允许作为人类输入、导出、快照和展示。导入必须通过显式 command 解析、预览 diff、确认并写入数据库；运行时不得自动从 Markdown 修复权威状态。

## 后果

- 作者仍可编辑 Markdown，但编辑不会绕过 validation/revision。
- 每个导出都带 project revision、schema version 和 checksum。
- Phase 7 完成后关闭 InkOS Markdown bootstrap compatibility path。

