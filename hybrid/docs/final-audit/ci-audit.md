# CI 审计

总体：`FAIL`。HEAD 的唯一正式 workflow 最近一次运行失败；拟议 Phase 9 workflow 未跟踪、从未运行，master 无 branch protection。

## 远端事实

- Repository：`2705911421/hybird`。
- HEAD run：`authority-gates` run `29245109368`，结论 `failure`。
- architecture job：PASS。
- InkOS typecheck/build/test job：PASS。
- Story Runtime job：FAIL，`2 failed, 94 passed`。
- 失败原因：Linux `NAME_MAX` 下 `"长目录" * 30` 作为单一路径组件，两个 migration fixture 测试抛 `Errno 36 File name too long`。
- `master` branch protection API：404 `Branch not protected`。

## 覆盖矩阵

| CI 能力 | HEAD 正式 CI | 状态 |
|---|---|---|
| TS unit/typecheck/build | 有，最近 PASS | PASS |
| Python unit/integration/contract/migration | 有全量 pytest，最近 FAIL | FAIL |
| architecture gates | 有，PASS | PASS |
| Studio frontend | build/unit 有 | PASS |
| browser E2E | 无 | FAIL |
| package/offline smoke | 无 | FAIL |
| Windows/macOS matrix | 无 | FAIL |
| Python min/max matrix | 仅 3.11 | FAIL |
| secret scan/license scan/SBOM/provenance | 无 | FAIL |
| benchmark/soak smoke | 无 | FAIL |
| release depends on complete CI | 无 release workflow in HEAD | FAIL |
| coverage threshold | 未定义 | PARTIAL（治理缺陷） |

未跟踪 `phase9-ci.yml` 声明了 Windows/Ubuntu/macOS、3.11/3.13、package smoke、pip/pnpm audit、gitleaks、SBOM 和 deterministic Studio benchmark，但声明不是执行证据。

本地 `pnpm audit --audit-level high`：FAIL，95 vulnerabilities（10 low、58 moderate、25 high、2 critical）。critical：`protobufjs 7.5.4` RCE、`vitest 3.2.4` UI server arbitrary file read/execute。

不存在 `continue-on-error` 掩盖当前失败；更严重的问题是关键门禁根本未进入正式 CI。触发发布红线 18。

