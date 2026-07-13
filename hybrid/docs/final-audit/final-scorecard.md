# 最终评分卡

最终得分：**36 / 100**  
发布结论：**NOT READY FOR PRODUCTION RELEASE**

| 领域 | 权重 | 状态 | 得分 | 主要理由 |
|---|---:|---|---:|---|
| 单一权威状态源 | 15 | FAIL | 0 | chapter list/analytics/export 仍以本地 index/Markdown 为事实 |
| 章节事务和幂等 | 15 | PARTIAL | 12 | 核心强；disk-full/orphan 未验证 |
| 事件、投影和恢复 | 10 | PARTIAL | 4 | replay 成立；`at_revision` 伪实现 |
| 长期上下文和一致性 | 10 | PARTIAL | 4 | 分层/trust好；LIKE lexical、`/4` token、占位压缩 |
| 审核与修订统一 | 8 | PARTIAL | 7 | typed E2E通过；产品主链未闭合 |
| Agent 权限和安全 | 8 | FAIL | 0 | symlink 可读 Runtime DB；read 无界 |
| 迁移可靠性 | 8 | PARTIAL | 4 | CIR/fixtures强；post-cutover rollback失败 |
| Studio/CLI/TUI 产品整合 | 6 | FAIL | 0 | 浏览器显示 0 chapters vs Runtime latest 3 |
| 性能和百万字能力 | 7 | PARTIAL | 3 | million已跑；lexical/commit SLO失败 |
| 稳定性和灾备 | 5 | PARTIAL | 2 | fault/restore/72s soak通过；24h/disk-full/upgrade缺失 |
| 安装、升级和发布 | 4 | FAIL | 0 | sidecar未接、无clean install/产品包 |
| CI、许可证和上游治理 | 4 | FAIL | 0 | HEAD CI失败、无保护、workflow未跟踪、audit critical |

## 触发的发布红线

1. 双 product authority：Runtime chapter store 与本地 chapter index/Markdown 分别决定不同用户输出。
2. migration cutover 后无法在实现内 rollback（红线 9）。
3. 许可证/源码/SBOM release bundle 未形成，provenance provisional（红线 16）。
4. E2E 主链失败：Studio 列表和 export 不反映 Runtime commit（红线 17）。
5. 正式 CI 当前失败且关键矩阵未运行（红线 18）。
6. `at_revision` 参数返回当前 entity，是伪历史查询（红线 19）。
7. 设计文档与实际产品读取路径严重不一致（红线 20）。

未触发/未发现：未知半提交、response-loss 重复提交、Agent 直接写 authority、Studio 直接开 Runtime DB、projection 无法 replay、Runtime 静默 legacy fallback。

