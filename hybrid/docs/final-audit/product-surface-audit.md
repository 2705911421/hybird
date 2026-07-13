# Studio、CLI、TUI 产品面审计

总体：`FAIL`。真实浏览器证明 Studio 的本地章节视图与 Runtime 状态不一致；export 同样绕过 Runtime finalized chapter store。

| 检查 | 状态 | 证据 |
|---|---|---|
| 三个 surface 共享 core interaction/pipeline | PARTIAL | CLI/TUI/Studio 大量共享 core；observability UI 有 Studio 专用 proxy |
| Studio 专属 authority 直写 | PASS | direct chapter PUT 被移除；typed diff 走 Runtime |
| CLI 绕过 review/Runtime | PASS | Runtime authority write/review tests |
| TUI 绕过 Runtime | PASS | shared interaction/pipeline；无单独 DB write |
| revision/commit 状态一致 | FAIL | 首页 0 chapters；Runtime revision 7/latest chapter 3 |
| degraded/recovery 状态 | PARTIAL | Runtime 页显示 degraded；首页未同步含义 |
| Studio 直接读 DB | PASS | proxy API，不开 SQLite |
| token 不泄漏浏览器 | PASS | proxy + redaction tests；browser requests 未见 token |
| event/commit 分页 | PASS | bounded query params + Studio views |
| deep doctor 高频轮询 | PASS | polling 分层/可见 refresh；未见 deep 高频请求 |
| 编辑人物/关系/伏笔 typed command | PASS | `/typed-diff` proxy |
| raw Truth authority | PARTIAL | Runtime books read-only；legacy books仍展示编辑能力 |
| webnovel Dashboard | PASS | architecture gate 隔离，无生产 import |
| Claude Code 必需 | PASS | build/test/package 不依赖 Claude Code |
| App 自动管理 Runtime | FAIL | process manager 无生产实例化 |

## 实际浏览器步骤

1. seed `lighthouse-project.json` 到 Runtime DB。
2. 启动 Runtime `47831` 与 built Studio `4567`。
3. Chromium 打开 Studio 首页：`The Lighthouse Fixture - 0 chapters`。
4. 点击 Runtime status：`Revision 7`、`Latest chapter 3`、`Indexed documents 3`。
5. console errors：0；相关 API 全 200，排除网络失败假象。

这表明错误来自产品数据所有权，而非页面加载失败。

## Export 缺陷

`export-artifact.ts:68` 调用 `loadChapterIndex`，随后 `readdir(chaptersDir)` 和 `readFile(...md)`。Runtime authority 的 finalized body 不在此路径，故可出现 Runtime 已成功提交但 export 报 `No chapters to export` 或导出陈旧正文。

结论：完整跨 Studio/CLI/TUI 操作和最终 export E2E 不通过，触发红线 17、20。

