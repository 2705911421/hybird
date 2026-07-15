# RC-1D-R2 Closeout Report

日期：2026-07-15
范围：F-002、F-003、F-004 与 RC-1 最终收口；未开始 RC-2。

## 当前判定

| Finding | 状态 | 判据 |
| --- | --- | --- |
| F-001 | CLOSED | Runtime-authority Writer recent narrative、正文集合与 revision 均来自 Runtime；A-F red-team 与 architecture gate 保持通过。 |
| F-002 | PARTIAL | 正式三 OS blocking workflow 与 release 依赖已提交到待验工作树；必须在 clean commit 和默认分支实际成功后才能关闭。 |
| F-003 | CLOSED | Studio Chromium 13 个浏览器黑盒场景和 TUI 13 个交互场景覆盖 A-F、七类 fault 与恢复，无 local fallback。 |
| F-004 | CLOSED | Runtime/legacy/importer mode-specific prompt 已修正并由 36 个 prompt 测试覆盖。 |

在默认分支的 `RC-1 Required Gate` 对最终提交实际成功前，整体结论保持：**RC-1D REMAINS BLOCKED**。

## F-004 关闭证据

Runtime authority system prompt 明确规定：章节集合、顺序、正文、摘要、最近叙事和 revision 只能来自 Story Runtime capability；Agent 不得用 file/read/grep/list 工具读取 `chapters/index.json` 或章节 Markdown 绕过 Runtime。local index/Markdown 只被描述为 legacy、显式 importer 输入或 export projection，且不是当前 authority。prompt 不暴露 Runtime DB 路径、表名或内部文件。

Legacy mode 保留了明确限于 legacy 项目的本地读取说明；importer mode 可描述 source files，但明确它们只是导入输入。Runtime fault 必须停止当前操作，不能切换到本地 owner。

## F-003 关闭证据

可提交 fixture orchestrator 固定 `project=rc1-ui-verification`、`revision=7`、Runtime chapters `1..3`、`latest=3`，并独立生成 A-F 六种本地状态。Studio 与 TUI 都由真实交互驱动，不是 formatter/helper 单测。

每种本地状态都验证 count/latest/revision 为 `3/3/7`、chapter 2 body/hash 来自 Runtime、chapter 4 与 local latest 99 不出现、analytics/search/export 使用 Runtime，且缺少 projection 不失败。connection refused、timeout、degraded、malformed DTO、version mismatch、authorization、DB locked 均显示明确错误，隐藏旧本地数据，阻止 export/write，并能在 Runtime 恢复后 retry。

详细矩阵见 `RC-1-UI-BLACKBOX-MATRIX.md`。

## F-002 实现与剩余外部验证

`.github/workflows/rc1-chapter-authority.yml` 现在是可复用的 `RC-1 Gate`，在 push、pull_request、workflow_call 上运行 Windows/Ubuntu/macOS，并包含 blocking aggregate `RC-1 Required Gate`。关键 jobs 均无 `continue-on-error`。`.github/workflows/release.yml` 先调用该 workflow，所有 release artifact jobs 都 `needs: rc1-gate`。

仓库当前 `master` branch protection API 返回 404（未保护）。代码不能替管理员启用 protection，因此不能宣称已经保护；管理员操作见 `RC-1-CI-GATE-REPORT.md`。这不改变 workflow 本身的 blocking 依赖，但合并保护仍需仓库管理员执行。

## 回归证据状态

dirty worktree 上的预检全部通过，但仅用于提交前排错，不作为最终放行证据：Runtime 113、Core 1572、CLI/TUI 219、Studio 503、Playwright 13，另有 architecture、typecheck、build 全部 exit 0。

正式证据将在实现提交后从 clean commit 重跑并回填：

- clean implementation commit：`PENDING_CLEAN_COMMIT`
- clean-commit local gate：`PENDING`
- default-branch GitHub Actions run：`PENDING`
- final closeout commit：`PENDING`

## 禁止项核对

未修改历史 Runtime event/revision，未重写 Studio，未修改章节事务，未新增 authority mode，未恢复 shadow writing，未降低 Runtime unavailable fail-closed 标准，未开始 RC-2。

## 最终放行条件

只有 clean commit 完整回归通过、工作区 clean、最终提交已推送且默认分支 `RC-1 Required Gate` 实际成功，F-002 才可改为 CLOSED，并输出 `RC-1D COMPLETE / READY FOR RC-1 FINAL GATE`。否则保持 `RC-1D REMAINS BLOCKED`。
