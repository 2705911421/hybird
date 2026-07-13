# Phase 9 performance report

## Evidence and method

The authoritative raw result is `phase-9-benchmark-windows.json`. It was produced on 2026-07-13 by CPython 3.11.15, SQLite 3.53.1 and Windows 10.0.26200 using seed `20260713`, 30 query samples and 15 normal commits. Corpus: 1,096,328 generated Chinese characters, 600 chapters, 320 characters, 3,200 relationships, 24,002 facts, 12,000 events, seven timelines and 420 threads. No LLM or copyrighted novel text was used.

Studio evidence is `phase-9-studio-benchmark-windows.json`: Chromium, five samples, deterministic local Runtime/Studio. It also found and drove fixes for a Runtime route bug and an uncontrolled polling loop.

## Measured baseline and SLO

SLOs are regression ceilings derived from the observed value with headroom; they are not claims about untested operating systems.

| Operation | Measured | Phase 9 SLO |
|---|---:|---:|
| Context/lexical P50 | 99.010 ms | <= 150 ms |
| Context/lexical P95 | 116.029 ms | <= 175 ms |
| Context/lexical P99 | 124.376 ms | <= 200 ms |
| Exact entity P50/P95/P99 | 8.174/9.861/10.327 ms | P95 <= 20 ms |
| Context response maximum | 34,691 bytes | <= 64 KiB |
| Layer token budget | 30/30 compliant | 100% compliant |
| Optional vector retrieval | not configured | no blocking SLO; must report status |
| Normal commit lifecycle P95 | 43.036 ms | <= 75 ms |
| Normal commit transaction P95 | 20.767 ms | <= 50 ms |
| Large (50k char) lifecycle P95 | 42.958 ms (3 samples) | <= 100 ms |
| Response-loss retry P95 | 6.481 ms | <= 15 ms |
| 12k-event replay verify | 768.743 ms | <= 1.5 s |
| Online snapshot | 967.480 ms | <= 2 s |
| Database/snapshot size | 23,703,552 bytes | capacity signal, not latency SLO |

Commit projection reducers execute inside the measured commit transaction. Separate reducer-only, lock-wait and continuous outbox-lag distributions are not yet emitted; their release SLOs are blocked until instrumentation produces samples. Busy wait is capped by the configured 750 ms timeout. Outbox is rebuildable but must not be allowed to remain pending indefinitely.

## Studio baseline and SLO

| Surface | Measured P50/P95 | SLO |
|---|---:|---:|
| First screen | 230/2,510.4 ms | cold P95 <= 3.5 s |
| Runtime overview | 42.9/57.2 ms | P95 <= 100 ms |
| Event page | 39.3/47.1 ms | P95 <= 100 ms |
| Commit list | 42.1/58.4 ms | P95 <= 100 ms |
| Commit detail | 35.9/46.3 ms | P95 <= 100 ms |
| Maximum JS heap | 43,077,207 bytes | <= 64 MiB in this flow |
| Transferred script/style | 2,661,814 bytes | <= 3 MiB |
| Built Studio directory | 14,876,736 bytes | <= 16 MiB |
| Main entry chunk | 2,527,362 bytes | warning threshold 2.75 MiB |

The browser fixture has only two displayed events; million-event UI pagination remains a required CI/release qualification even though the Runtime query plan uses the `(project_id, sequence)` index.

## Query plans and optimization proof

- Facts: `facts_project_active_idx (project_id, valid_to_revision, fact_id)`.
- Events: `story_events_project_sequence_idx (project_id, sequence)`.
- Chapter documents: `retrieval_documents_project_chapter_idx`.
- Chinese lexical candidates use a rebuildable FTS5 trigram index instead of loading all documents into Python.
- Facts are filtered in SQLite before deterministic Python scoring. Revisions, validators and commit transactions remain intact.

Pydantic query validation P95 was 0.050 ms and serialization P95 0.543 ms. Zod, HTTP protocol overhead separated from proxy time, WAL growth under sustained writes, and vector growth remain unmeasured release evidence gaps.
