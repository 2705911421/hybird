# RC-1 回归门禁

## CI 入口

`.github/workflows/rc1-chapter-authority.yml` 在 push 与 pull request 上运行。门禁不是单一字符串搜索：Python gate 检查 Python/TypeScript 结构和 import 约束，TypeScript gate 构建生产模块 AST、local import edges、call sites 及 Runtime adapter 方法可达图。

## 必须执行的 gate

| Gate | 命令 | 阻止的回归 |
| --- | --- | --- |
| Python architecture | `python hybrid/scripts/check_architecture.py` | Runtime storage 直读、Markdown bootstrap、重复 authority writer、Runtime LLM/import 越界 |
| TS authority call graph | `pnpm --dir inkos check:chapter-authority` | Runtime route/pipeline/context/export/analytics 本地 authority 调用、legacy fallback、route mode branching、`shadow`、fallback flag |
| Runtime read/export matrix | `python -m pytest hybrid/story-runtime/tests/unit/test_chapter_reads.py -q` | revision/checksum、分页、export snapshot、commit 并发隔离 |
| Application service matrix | Core targeted Vitest | local absent/0/2/4/checksum mismatch/latest 99/projection deleted、handshake、401、invalid mode |
| CLI/TUI parity | CLI targeted Vitest | chapter browser/detail/stats 与 unified service、无 route-level authority 选择 |
| Studio API matrix | Studio `server.test.ts` | unavailable write-next、typed errors、Runtime/local conflict |
| Full Python/contracts | `python -m pytest -q` | Runtime 与 approved contracts 全量回归 |
| Full TS | `pnpm typecheck && pnpm build && pnpm test` | core、CLI、Studio、TUI 全量回归 |
| Chromium | Playwright Chromium project | Studio 真实浏览器工作流与 API/client 集成 |

## RC-1D 本地状态矩阵

以下状态必须产生同一个 Runtime revision 结果：

| 状态 | 断言 |
| --- | --- |
| local absent | list/detail/analytics/export 正常，不创建本地 authority 文件 |
| local 0 | Runtime count/latest 胜出 |
| local 2 | Runtime collection 胜出 |
| local 4 | local 伪章不进入 list/search/export |
| local checksum mismatch | Runtime body 与 checksum 胜出 |
| local latest 99 | Runtime latest/revision 胜出 |
| projection deleted | Studio/CLI/TUI 仍可读取 Runtime |
| Runtime unavailable | typed failure，写入与读取均 fail closed |
| malformed Runtime | contract mismatch，绝不读 local |
| export during commit | snapshot 保持单一 revision，不混入并发 commit |

## 失败策略

任一 gate 失败即阻止 RC-1 发布。修复方法只能是恢复统一 application-service/Runtime 调用链或修正合同；不得通过放宽 gate、重新启用 local fallback、恢复 `shadow` 或把 local projection 标记为 current 来通过测试。
