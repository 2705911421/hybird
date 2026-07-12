# Phase 1 baseline performance

Measured 2026-07-12 on Microsoft Windows 11 Home China, Python 3.11.15, Intel Core i5-1135G7. The benchmark uses a temporary WAL database and the deterministic `lighthouse-project` fixture. No network, LLM, embedding, or reranker is involved.

Command:

```text
set PYTHONPATH=src
python scripts/benchmark.py --iterations 500
```

| Operation | Median | P95 | Iterations |
|---|---:|---:|---:|
| Exact entity query with history | 12.085 ms | 19.510 ms | 500 |
| Governed fact + local RAG context query | 18.033 ms | 30.889 ms | 500 |

This is a Phase 1 fixture baseline, not a million-word capacity claim or release SLO. Phase 3 owns synthetic million-word, context-size, and long-running performance gates. The benchmark intentionally opens and closes short-lived connections to exercise the supported Windows lifecycle.
