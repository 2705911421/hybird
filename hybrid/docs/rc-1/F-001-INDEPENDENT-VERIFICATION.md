# F-001 独立验收报告

日期：2026-07-15（Asia/Shanghai）
范围：仅验证 `F-001：Runtime-authority writer directly reads local chapter Markdown`；未修改业务代码。

## 验收方法

按 `RC-1B-R2` 红队定义执行 Core 测试：

```text
pnpm --filter @actalk/inkos-core exec vitest run \
  src/__tests__/chapter-application-service.test.ts
```

结果：1 个测试文件、20 tests 全部通过。测试使用 deterministic writer stub 捕获最终输入，不调用 LLM。Runtime fixture 为 `runtime-book`、revision `7`、Runtime finalized chapters `1..3`。

## Case A-F 实测结果

| Case | 本地 Markdown/投影扰动 | Stub 最终 Writer input | 结果 |
|---|---|---|---|
| A | 无 chapter Markdown | `authorityMode=runtime`, `source=runtime`, `projectRevision=7`, latest `3`, chapters `1..3` | PASS |
| B | 本地伪造 chapter 2 | 仅包含 Runtime chapter 2 body；伪造文本不在序列化 input | PASS |
| C | 本地伪造 future chapter 4 | latest 仍为 `3`；无 chapter 4 | PASS |
| D | 本地 latest/index=99 | latest/revision 仍为 Runtime `3/7` | PASS |
| E | 本地顺序与 Runtime 不同 | 输入按 Runtime order `1..3` | PASS |
| F | 本地正文含 prompt injection | injection 不在序列化 input | PASS |

测试同时断言 local chapter reader mock 未被调用，并断言 Runtime `/chapter-export` 请求携带 `expected_revision=7`、`from_chapter=1`、`to_chapter=3`。

## 逐项验收

1. **Recent narrative 来源**：`ProjectWriterNarrativeContextResolver` 在 `authorityMode === "runtime"` 时只选择 `StoryRuntimeWriterNarrativeContextAdapter`；该 adapter 通过 `ChapterExportPort.exportSnapshot` 取 Runtime 数据。A-F 捕获输入均为 `source=runtime`。通过。
2. **Revision 绑定**：`PipelineRunner` 先读取 Runtime status，再以 `expectedRevision: runtimeStatus.revision` 调用 narrative resolver，并将同一 `narrativeContext` 传入 `WriterAgent.writeChapter()`；测试实际验证 revision `7` 及 export 请求字段。通过。
3. **WriterAgent Runtime filesystem reader**：WriterAgent 仅消费 `input.narrativeContext`；无 `loadRecentChapters`、`readFile`/`readdir` chapter reader。通过。
4. **本地 Markdown 缺失**：Case A 通过，且 local reader 未调用。通过。
5. **本地 Markdown 冲突**：Cases B、D、E 通过，伪造 body/index/order 不进入 input。通过。
6. **本地 fake future chapter**：Case C 通过，chapter 4 不进入 input。通过。
7. **本地 malicious text**：Case F 通过，注入文本不进入 input。通过。
8. **Runtime unavailable**：测试断言 resolver rejects `code=runtime_unavailable`，且 `loadChapterIndex` 未调用；无 Legacy fallback。通过。
9. **Legacy 项目**：`LegacyWriterNarrativeContextAdapter` 是独立显式 adapter；resolver 仅在 `authorityMode` 缺省或 `legacy` 时选择它，Runtime 分支不触达该 adapter。通过（静态代码核验）。
10. **Architecture gate 主动拦截**：

```text
pnpm run check:chapter-authority
```

基线结果：`Runtime chapter authority AST gate passed (439 modules, 319 import edges, 23996 call sites)`。

随后仅在临时工作副本中向 `WriterAgent` 注入 `import { readdir } from 'node:fs/promises'`，未保留任何业务改动；gate 返回 exit `1` 并报告：

```text
packages/core/src/agents/writer.ts: WriterAgent imports a chapter-directory filesystem reader
```

恢复后工作树中的 Writer 内容与注入前一致。通过。

## 结论

# F-001 VERIFIED CLOSED
