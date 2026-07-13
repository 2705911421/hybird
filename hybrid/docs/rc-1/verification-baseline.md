# RC-1C Verification Baseline

验证日期：2026-07-14（Asia/Shanghai）  
验证范围：RC-1B Runtime authority 产品读取、跨 surface 一致性、故障与投影删除行为。  
验收原则：本次只观察和记录，不修改业务代码、测试预期或运行时数据。

## Repository

| 项目 | 值 |
| --- | --- |
| commit | `d727dd4cd0589bdb856046e92994fa8a5141ef46` |
| branch | `master` |
| git status | dirty；91 行变更，包含既有 RC-1B/Phase 9 工作树变更；本次未清理或回滚 |
| Node / pnpm | `v24.16.0` / `9.12.0` |
| Python | `3.11.15` |
| InkOS | `1.7.0` (`inkos/package.json`) |
| Story Runtime | `0.1.0` (`hybrid/story-runtime/pyproject.toml`) |

## Runtime Contract

| 项目 | 值 |
| --- | --- |
| Runtime API | `/api/story-runtime/v1` |
| contract schema | `story-runtime/v1` |
| SQLite schema migration | `7` |
| fixture project | `rc1-verification` |
| fixture revision | `7` |
| finalized chapters | `1, 2, 3`；latest `3` |
| chapter 2 SHA-256 | `b8ea99c4533dbe44650dda84f83dbfb76fd5332e6396cf8d7ba5463c8f04c1fa` |
| collection SHA-256 | `34b88b4013435d7e9d22714e738b13b53ddcb2a2dfe233d9a3ebe568caa67722` |

## Flags and Authority

本 shell 未设置 `STORY_RUNTIME_*` 或 `INKOS_*` 环境变量，故使用代码默认值：

| 设置 | 值 |
| --- | --- |
| `STORY_RUNTIME_ENABLE_WRITES` | `0` |
| `STORY_RUNTIME_UNIFIED_REVIEW_ENABLED` | `0` |
| `STORY_RUNTIME_OBSERVABILITY_ENABLED` | `1` |
| `STORY_RUNTIME_RECOVERY_ENABLED` | `1` |
| `STORY_RUNTIME_MIGRATION_ENABLED` | `1` |
| `fallbackOnUnavailable` | `false` |

Runtime fixture 的 `authority_mode` 为 `runtime`。另建 legacy fixture 验证明确的 `LegacyChapterReadAdapter`：CLI 返回 `authority=legacy`、revision `0`，并从本地 Markdown 读取；该路径未作为 Runtime authority 的成功路径计分。

## Commands Executed

已执行并记录结果：

* `python hybrid/scripts/check_architecture.py`：passed。
* `pnpm check:chapter-authority`：passed。
* Runtime targeted tests、Runtime full pytest：passed。
* Core chapter/export targeted tests：4 passed。
* Studio `server.test.ts`：130 passed。
* InkOS typecheck、build：passed。
* `pnpm test`：failed，CLI 38 files 中 37 passed，205 tests 中 203 passed、2 failed（English `7 words` 实际 `0 words`；degraded `1800字` 实际 `0字`）。

黑盒、故障、删除投影和 Chromium 证据保存在 `output/rc1-verification/`；最终判定见 `RC-1C-VERIFICATION-REPORT.md`。
