# 上下文与长期记忆审计

总体：`PARTIAL`。分层、trust 与权威事实优先真实存在；检索只是 lexical/SQL LIKE，不是完整 RAG，token 与“压缩”实现不足以支撑严格百万字治理。

## 分层

`hard_constraints -> plot_commitments -> relevant_memory -> recent_narrative -> style_guidance`：`PASS`，见 `services.py:65-164`。

| 检查 | 状态 | 证据 |
|---|---|---|
| authoritative facts 先于 retrieval | PASS | `query_context` 先 query facts |
| RAG 不覆盖权威事实 | PASS | retrieval 标记 `untrusted_content` |
| 冲突显式返回、不静默选值 | PASS | `_detect_conflicts` + active fact conflicts |
| 最近章节窗口有界 | PASS | recent summaries/documents query |
| 全量注入禁止 | PARTIAL | max items/tokens 有界；compat arrays 另行返回 |
| token budget 硬限制 | PARTIAL | 字符上限实现，但非真实 tokenizer |
| 中文 token 可靠 | FAIL | JSON 字符数 `(len+3)//4`，`services.py:164` |
| 目标模型 tokenizer | FAIL | 未使用 |
| 无 tokenizer 安全上界 | FAIL | `max_tokens * 4` 对中文不是安全上界 |
| 语义压缩 | FAIL | 低优先项替换为 `Compressed reference:` 占位符，`services.py:267-286` |
| trace 可解释/来源/trust/confidence/time | PASS | `ContextItem`/`QueryTrace` |
| prompt injection 隔离 | PARTIAL | trust 标记存在；未证明所有 Composer prompt 强制隔离 |
| alias recall | PARTIAL | entity IDs/alias structured query；规模 alias recall 未量化 |
| Runtime unavailable fail closed | PASS | Runtime authority 不 fallback legacy |

## 检索分类

- Authoritative facts：SQL active facts + term `LIKE`，再做词项重叠排序。
- Retrieval documents：本地 lexical/FTS 支持；当前 benchmark 报 `optional_vector=not_configured`。
- 不具备 BM25、vector、hybrid fusion 或 rerank 的完整生产证据。

正式分类：`lexical + SQLite FTS/LIKE`；不是完整高级 RAG。

百万字实测：exact P95 `16.562 ms`（PASS 该局部 SLO）；lexical P95 `189.231 ms`，超过仓库 `175 ms` SLO（FAIL）。

