# RC-1 UI Black-box Matrix

## Fixture contract

`hybrid/fixtures/rc1-ui-verification/orchestrator.mjs` 是 Studio 与 TUI 共用的确定性 fixture。它不读取开发机既有项目、不调用真实 LLM，并可用 `prepare`、`fault`、`serve` 子命令独立复现。

| 字段 | 固定值 |
| --- | --- |
| project | `rc1-ui-verification` |
| Runtime revision | `7` |
| Runtime chapters | `1..3` |
| Runtime latest | `3` |
| chapter 2 body | `Runtime chapter two authority sentinel.` |

## Local A-F matrix

| Case | 本地扰动 | Studio Chromium | Interactive TUI | 权威结果 |
| --- | --- | --- | --- | --- |
| A | 无 index、无 Markdown | PASS | PASS | count/latest/revision = 3/3/7 |
| B | index=0 | PASS | PASS | 同上 |
| C | index=2 | PASS | PASS | 同上 |
| D | index=4 + fake chapter 4 | PASS | PASS | chapter 4 不出现 |
| E | local chapter 2 checksum/body 冲突 | PASS | PASS | Runtime body/hash 胜出 |
| F | local latest=99 | PASS | PASS | latest 仍为 3 |

Studio 每个 case 实际驱动 homepage、chapter list、chapter detail、analytics、search、export、project reopen；TUI 每个 case 通过 Ink stdin 实际驱动 `/chapters`、`/chapter 2`、`/stats`、`/search`、`/export`。两者都核验 Runtime chapter 2 SHA-256，export count=3，并拒绝 local fake/conflicting body。

## Runtime fault matrix

| Fault | Studio | TUI | Fail-closed 断言 | Recovery |
| --- | --- | --- | --- | --- |
| connection refused | PASS | PASS | 明确 unavailable；无旧章节/export/write | retry PASS |
| timeout | PASS | PASS | 明确 timeout/unavailable；无 fallback | retry PASS |
| degraded | PASS | PASS | compatibility handshake 拒绝 | retry PASS |
| malformed DTO | PASS | PASS | contract error；无 projection fallback | retry PASS |
| version mismatch | PASS | PASS | version mismatch；无 fallback | retry PASS |
| authorization | PASS | PASS | unauthorized；不可切换 owner | retry PASS |
| DB locked | PASS | PASS | locked；无旧数据/export/write | retry PASS |

Studio 故障态不呈现 chapter 4，不显示 export/write-next 按钮，并明确说明 export blocked / writes disabled。TUI 故障态不显示本地 chapter 4/latest 99，`/retry` 在 Runtime 恢复后重新显示 `3/3/7`。

## Commands

```text
pnpm --filter @actalk/inkos test -- tui-chapter-surface.test.ts tui-rc1-interaction.test.tsx
pnpm --filter @actalk/inkos-studio test:e2e:rc1 -- --project=chromium
```

clean commit `b95298f36c44f447ce5a5d7d10c46d97e8767935` 正式结果：TUI targeted 14/14 passed（34.85s，包含 build）；Playwright Chromium 13/13 passed（134.35s）。在发现 fresh checkout 需要显式 Core prebuild 后，clean commit `6df3c5e02931ba51f7970914a7d8ee61604fdaed` 又以 CI 完全相同的 package script 验证 13/13 passed（114.48s）。命令均 exit 0，fixture 临时目录已删除，工作树保持 clean。
