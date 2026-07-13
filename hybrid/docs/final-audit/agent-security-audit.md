# Agent 权限与安全边界审计

总体：`FAIL`。未发现 Agent 可直接写 Runtime authority，但已实际证明默认 read tool 存在 symlink 真实路径绕过，可读取伪装为 `.txt` 的 Runtime DB；同时 read 结果无大小上限。

## 工具清单

生产 Agent tools：`propose_action`、`sub_agent`、`research_web`、`ingest_material`、`retrieve_material`、`short_fiction_run`、`translation_create`、`script_create`、`storyboard_create`、`interactive_film_create`、`generate_cover`、`play_start`、`play_edit`、`play_step`、`play_revise`、`read`、`grep`、`ls`。

未发现 shell、任意 SQL、SQLite writer、raw Runtime event tool：`PASS`。

## 边界结果

| 检查 | 状态 | 证据 |
|---|---|---|
| 直接写 Runtime DB/Truth/migration snapshot | PASS | 无此 Agent tool；authority path deny |
| 任意 SQL/shell | PASS | 工具清单无对应能力 |
| 通过 Runtime command 写长篇 | PASS | `sub_agent` 最终走 pipeline/Runtime commit |
| `../` 路径 | PASS | `safeChildPath` lexical traversal test |
| DB 扩展/known runtime path deny | PASS | `agent-tools.ts:2392-2398` |
| symlink bypass | FAIL | 最小实测见下 |
| absolute system read | PARTIAL | `INKOS_AGENT_ALLOW_SYSTEM_READ=1` 可启用任意绝对路径读取，只有少量黑名单 |
| 超大 artifact | FAIL | 单测明确要求 `read` 不截断 10,500+ 字符；生产代码无 byte limit |
| nested payload/Runtime request size | PASS | Runtime middleware 有 `max_request_bytes` |
| prompt injection | PARTIAL | review 侧作为 prose；全 Agent tool routing 未完成攻击链 E2E |
| Unicode 路径混淆 | PARTIAL | CJK migration 有覆盖；Agent normalization/realpath 未覆盖 |
| 最小权限 | FAIL | read 权限采用路径字符串黑名单，非 handle/realpath allowlist |

## 实际攻击

执行最小 Node 诊断：在 `books/` 内创建 `innocent.txt` 文件 symlink，目标是外部 `story.db`；然后调用默认 `createReadTool(root)`。

结果：`{"text":"AUTHORITY_DB_SENTINEL"}`，即 `FAIL`。原因是 `safeChildPath()` 只做 `resolve/relative`，`resolveReadPath()` 又只检查 symlink 名字，不检查 `realpath` 或打开后的文件身份。

这次攻击只证明读取 authority，不证明 Agent 可修改 authority，因此发布红线 5（Agent 直接修改 authority）未被该证据单独触发。但它足以使 Agent 安全领域 FAIL，并可能泄漏正文、SQLite 内容或密钥。

其余攻击项：伪造正文系统指令、malformed JSON、stale evidence 有单元测试；伪造 tool name、深层 payload、完整 prompt-to-tool 越权没有独立 E2E，`NOT VERIFIED`。

## 必须修复

对所有文件工具使用 `realpath`/open-handle 后 containment 与文件类型 allowlist；禁止跟随 symlink/reparse point；设置单次/总会话 byte 上限；移除或强约束 system read feature flag，并增加 Windows junction/symlink、CJK、NT path 前缀攻击测试。

