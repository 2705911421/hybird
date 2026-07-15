# RC-1B Runtime unavailable 策略

## Typed failures

| Application error | 条件 | Retryable |
|---|---|---|
| `runtime_unavailable` | Runtime stopped、网络失败、未配置 adapter | 是 |
| `runtime_timeout` | 请求取消/超时 | 是 |
| `database_locked` | Runtime 返回 `DATABASE_LOCKED` | 是 |
| `revision_changed` | cursor/export expected revision 不一致 | 是，重新开始操作 |
| `runtime_contract_mismatch` | DTO 无法通过 Zod/Pydantic contract | 否，修复版本/合同 |
| `runtime_version_mismatch` | Runtime 返回 `VERSION_MISMATCH` | 否，升级匹配版本 |
| `runtime_unauthorized` | Runtime 返回 401/403 | 否，修复凭证或授权 |
| `invalid_authority_mode` | 配置或项目 authority 不在允许集合 | 否，修复配置；不得猜测 fallback |
| `checksum_mismatch` | Runtime body 与 body SHA-256 不一致 | 否，阻断当前结果 |
| `not_found` | Runtime 不存在 project/chapter | 否 |

## Surface 行为

- 读取：显示 unavailable/typed error，不返回本地 chapter/index/memory 为当前结果。
- 写入：fail closed；rewrite、resync、本地编辑等 legacy 写路径在触碰本地章节前返回 Runtime typed-command/replay 要求。
- Export：失败，不使用本地 Markdown 静默生成。
- Studio：HTTP 映射保持错误 code 与 retryable 信息；不把 unavailable 伪装为 404。
- CLI：输出 error 并返回非零退出码。
- TUI：追加明确的 `Runtime unavailable` system message，当前章节读写视为禁用。

## Stale cache

RC-1D 不启用 stale chapter cache 展示，也没有 stale cache 自动刷新生产路径。未来若启用，必须显示 `stale=true`、cached revision 和 verified timestamp，且不得用于写入、current analytics 或默认 export。离线 verified export snapshot 也必须显式显示 snapshot revision；当前默认仍为失败。

## 禁止 fallback

Resolver 对 `authorityMode=runtime` 只返回 Runtime adapter。任何 surface 都不得因上述错误实例化或调用 `LegacyChapterReadAdapter`。`shadow`、未知 mode 和遗留 `fallbackOnUnavailable` 均不是合法 production 配置。Architecture gate 与 Core tests 检查这些不变量。
