# 代码质量审计

总体：`PARTIAL`，并包含供应链 blocker。

## 规模与维护性

| 文件 | 行数 | 判断 |
|---|---:|---|
| `studio/src/api/server.ts` | 6,274 | FAIL：过大，混合路由、file I/O、Runtime proxy、产品域 |
| `core/src/agent/agent-tools.ts` | 2,555 | FAIL：权限边界与大量产品工具混合 |
| `core/src/pipeline/runner.ts` | 2,065 | PARTIAL：核心 orchestration 过大 |
| `studio/src/components/ai-elements/prompt-input.tsx` | 1,457 | PARTIAL |
| `core/src/llm/provider.ts` | 1,414 | PARTIAL |
| `story_runtime/migration_jobs.py` | 1,191 | PARTIAL：安全扫描、CIR、import、rollback 混合 |

## 质量检查

| 检查 | 状态 | 证据 |
|---|---|---|
| duplicate DTO/schema | PARTIAL | Pydantic/JSON/Zod 三份，contract tests 降低但不消除 drift |
| duplicate mode/error strings | FAIL | TS Zod 接受 shadow，CLI/Studio 拒绝；legacy 字符串分散 |
| implicit globals/in-memory state | PARTIAL | Studio create status/maps 为内存状态；commit authority 持久 |
| sync blocking I/O | PARTIAL | Python SQLite 同步；FastAPI sync handlers 可接受但需容量评估 |
| unbounded lists/results | FAIL | Agent read 无 byte limit；多个 Studio routes 读完整 files/logs |
| log/snapshot rotation | PARTIAL | Runtime rotation 配置存在；24h 未验证 |
| connection cleanup | PASS | Runtime context manager + tests；Play DB finally fix |
| broad `except Exception` | PARTIAL | commit recovery/observability/migration 多处；部分有 durable boundary 理由 |
| empty catch/silent fallback | PARTIAL | Studio 大量 catch-to-default；legacy outline fallback 可达 |
| schema/config version centralized | PARTIAL | Runtime 常量集中；TS/Python/JSON 仍重复 |
| production TODO | PASS | 搜索未发现实质 production TODO（测试/注释例外） |
| permanent feature flags | FAIL | Runtime mode schema 仍含 `legacy/shadow`；input governance legacy 可配置 |
| dead/exported code | PARTIAL | `executeEditTransaction` 导出、无生产调用 |
| circular/unused dependencies | NOT VERIFIED | 未运行专用 dependency graph/unused analyzer |
| upstream provenance/license | FAIL | legal status provisional；release license bundle未生成 |
| secrets | PARTIAL | Runtime logs redaction tests通过；gitleaks 未正式运行 |
| dependency vulnerabilities | FAIL | pnpm audit 2 critical + 25 high |
| mocks vs real boundaries | PARTIAL | Runtime real SQLite tests强；Studio 主链大量 mock，浏览器暴露未覆盖缺陷 |

最大问题不是风格，而是文件边界过大导致同一 owner 修复需要同时触碰 Runtime proxy、本地文件兼容和产品呈现，直接增加“缝合”风险。

