# ADR-007：Agent 不得直接修改持久状态

- 状态：Accepted
- 日期：2026-07-11

## 背景

InkOS Agent 工具有 truth/file write；webnovel-writer 的保护依赖 Claude hook。Prompt Injection 或错误 extraction 可借此污染长期状态。

## 决策

Agent 仅生成 schema-validated proposal、正文和 evidence；只有 Runtime command handler 能写 authority。通用 read/edit/write 工具不得访问 Runtime 内部路径，Claude/宿主 hook 不作为安全边界。

## 后果

- 所有事实变化可追溯到 request、Agent proposal、validator 和用户/策略决策。
- 会增加一次 prepare/validate 往返，但换取可审计性。
- Studio truth editor 必须转换为 typed diff command。

