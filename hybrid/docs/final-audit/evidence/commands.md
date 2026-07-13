# 审计命令与结果索引

| 命令/动作 | 结果 |
|---|---|
| `python hybrid/scripts/check_architecture.py` | PASS：10 rules + dashboard isolation |
| `python -m pytest`（Runtime 全套） | 107 passed（当前 Windows 工作区） |
| `pnpm typecheck` | PASS |
| core Vitest 顺序复跑 | 171 files / 1545 tests PASS |
| `pnpm --filter @actalk/inkos-studio test` | 58 files / 497 tests PASS，75.42s |
| `pnpm --filter @actalk/inkos test` | 38 files / 205 tests PASS，144.72s |
| 根 `pnpm test` | 244s 工具超时；分包结果如上，不能记为聚合命令 PASS |
| `pnpm build` | PASS，115.4s；Studio 2.53MB 主 chunk warning |
| failure matrix | 11/11 PASS |
| typed review E2E | 1/1 PASS |
| migration selection | 14/14 PASS |
| Phase 9 stability | 8/8 PASS |
| million benchmark | 完成；见 `performance-million-windows.json`，3 项关键 SLO FAIL |
| 0.02h soak | 326 iterations、0 errors；见 JSON |
| PyInstaller build + EXE `--help` + `/health` | PASS（当前 Windows 开发机） |
| Chromium Studio audit | FAIL：0 chapters vs Runtime latest 3；console 0 errors |
| symlink Agent attack | FAIL：通过 `innocent.txt -> story.db` 读出 sentinel |
| `pnpm audit --audit-level high` | FAIL：95 vulnerabilities，2 critical、25 high |
| `gh run view 29245109368` | FAIL：Runtime 2 tests fail；InkOS/architecture pass |
| branch protection API | FAIL：master not protected |

未执行：真实 disk-full、24h soak、macOS/Linux clean install、完整产品 upgrade/downgrade/rollback、签名安装器、正式 SBOM/gitleaks/pip-audit、真实 LLM（按要求使用 deterministic/offline 路径）。

