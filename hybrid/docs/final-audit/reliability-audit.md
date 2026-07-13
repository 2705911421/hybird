# 稳定性与灾备审计

总体：`PARTIAL`。事务故障、snapshot/restore、projection repair 和短 soak 有实测；24h、真实 disk full、schema migration failure、真实 upgrade/rollback 未完成。

## 实测

- 72.187 秒 soak：326 iterations、33 commits、99 outbox completed、3 retries、0 errors、0 harness leaked processes。
- Phase 9 stability tests：8/8 PASS（snapshot/restore、WAL checkpoint、DB pragmas、version mismatch 等）。
- fault matrix：11/11 PASS。
- Windows process lifecycle unit/integration：PASS。
- Windows standalone health：PASS；27,660,862-byte EXE。
- 手工停止 PyInstaller 启动父 PID 后仍观察到 child PID 20820，随后已清理：`PARTIAL`。产品 process manager 若接线可按 process tree 处理，但当前产品未接线。

## 灾备项目

| 项目 | 状态 | 说明 |
|---|---|---|
| DB integrity/checkpoint | PASS | tests + benchmark checkpoint |
| snapshot/restore 新目录 | PASS | stability test，projection hash 一致 |
| projection corruption/replay | PASS | doctor/recovery integration |
| outbox backlog/retry | PASS | fault matrix；million 结束仍 pending 54 |
| Runtime 多次 restart | PASS（测试） | process lifecycle tests |
| Studio 多次 reconnect | PARTIAL | polling tests；未长时真实浏览器循环 |
| stale PID/orphan cleanup | PASS（manager tests） | 但 manager 未接入产品 |
| memory/handle leak | PARTIAL | 72 秒无 harness leak；handles 在 soak 为 null |
| WAL/log/snapshot 无界增长 | PARTIAL | rotation/checkpoint 配置存在；24h 未验证 |
| disk full | NOT VERIFIED | 未在隔离卷模拟 ENOSPC |
| schema migration failure | NOT VERIFIED | 缺少失败后自动回滚的真实升级测试 |
| app/runtime mismatch | PASS（contract test） | package/product launch 未统一 |
| 24h soak | NOT VERIFIED | workflow 未跟踪且无可验证 artifact |
| backup restore | PASS（测试） | clean-machine operator drill 未执行 |

证据：`evidence/soak-windows-0.02h.json`、package smoke logs、`tests/integration/test_phase9_stability.py`。

