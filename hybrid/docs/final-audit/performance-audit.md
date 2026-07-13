# 性能与容量审计

总体：`PARTIAL`。百万字 deterministic corpus 已真实执行，不能再标记“未测试”；但核心查询和 commit 超过仓库自定 SLO，不能宣称性能通过。

证据：`evidence/performance-million-windows.json`。

## Corpus

| 指标 | 实测 |
|---|---:|
| 中文字符 | 1,096,328 |
| 章节 | 600 |
| 人物 | 320 |
| 关系 | 3,200 |
| facts | 24,002 |
| events | 12,000 |
| narrative threads | 420 |
| 特性 | CJK filename、emoji、多卷、conflicting facts |

固定 seed `20260713`，无版权 synthetic templates。

## 指标

| 指标 | P50/P95/P99 或值 | 状态 |
|---|---|---|
| exact query | 10.363 / 16.562 / 18.790 ms | PASS |
| lexical retrieval | 127.794 / 189.231 / 197.541 ms | FAIL（SLO 175ms） |
| normal commit lifecycle | 44.678 / 782.106 / 782.106 ms | FAIL（SLO 75ms） |
| normal transaction | 17.179 / 342.551 / 342.551 ms | FAIL（SLO 50ms） |
| large commit lifecycle | 70.003 ms P95 | PARTIAL |
| response-loss retry | 11.003 ms P95 | PASS |
| 12k replay verify | 1,120.01 ms，hash matched | PASS |
| snapshot | 1,771.251 ms | PASS（单机测量） |
| DB/snapshot size | 23,703,552 bytes | PASS（测量） |
| outbox pending | 54 | PARTIAL（benchmark 结束仍有 backlog） |
| vector/hybrid/rerank | not configured | NOT VERIFIED |
| memory/open handles/process | benchmark 未完整测 | NOT VERIFIED |
| Studio pagination | 浏览器功能可用；规模延迟未在本轮重跑 | PARTIAL |
| cold start/restart/migration | 非统一 million lifecycle 测量 | NOT VERIFIED |

corpus 由 fixture 直接灌入 Runtime，不代表 600 章逐章经过 InkOS Agent/review/commit。性能结果只能证明 Runtime 数据规模，不证明全产品百万字持续创作 SLO。

结论：百万字测试已执行，但正式性能目标未达成。

