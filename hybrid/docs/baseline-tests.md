# 上游测试基线

测试日期：2026-07-11（Asia/Shanghai）。未为通过测试修改任何业务行为。

## 环境

| 工具 | 版本 |
|---|---|
| OS | Windows |
| Node | v24.16.0 |
| pnpm | 9.12.0 |
| Python | 3.11.15 |
| pytest | 9.1.1 |
| Pydantic | 2.13.4 |

## InkOS `fd87b04`

1. `pnpm.cmd install --frozen-lockfile`：通过；未修改 lockfile。
2. `pnpm.cmd test`：通过（core、studio、CLI 三个 workspace package 全部成功；CLI 可见汇总为 38 files / 209 tests passed）。总耗时约 276 秒。
3. `pnpm.cmd build`：通过。Studio Vite 转换 5043 modules；有 chunks >500 kB 警告，主 bundle 约 2.48 MB（gzip 715 kB），不影响退出码。
4. `pnpm.cmd typecheck`：core、studio client/server、CLI 全部通过。

构建/测试产生的 `node_modules` 与 `dist` 均为上游忽略产物；上游 git status 保持 clean（最终检查见下）。

## webnovel-writer `59654cc`

### 默认命令

`python -X utf8 -m pytest -q`：失败。

- coverage：86%，低于 `fail-under=90`。
- 同时存在功能失败与 fixture setup error，不只是 coverage 门槛。

### 去掉 coverage 后的行为计数

`python -X utf8 -m pytest -q --no-cov --tb=no --no-summary --disable-warnings`：

- 714 passed
- 28 failed
- 32 errors
- exit code 1

主要根因：

1. `webnovel-writer/scripts/conftest.py:57` 的 `_SafeTemporaryDirectory` 向 Python 3.11 `TemporaryDirectory.__init__()` 传入不支持的 `delete` 参数，导致 `test_data_modules.py` 的 32 个 setup error。仓库 requirements 注释声明 Python >=3.10，因此这是当前基线兼容缺陷。
2. 多个 `reference_search` / `validate_csv` / behavior eval 测试在 Windows 子进程输出解码中产生 `UnicodeDecodeError`，并造成 CSV/reference 搜索断言失败。
3. `test_run_behavior_evals_fast_suite_passes_for_current_package` 随上述行为失败。

本阶段不修复这些问题。Phase 0 应在 Python 3.10/3.11/3.12/3.13 和 Windows/Ubuntu 建矩阵，把环境缺陷与真实逻辑缺陷拆分。

## Hybrid contracts

内联只读校验脚本完成：

- 15 个 JSON Schema 均通过 Draft 2020-12 meta-schema 检查。
- 所有本地 JSON `$ref` 文件存在。
- OpenAPI YAML 可解析，版本为 3.1.0。
- 12 个必需 operation 均存在。
- 7 个写请求 schema 均引用 `common-write-context.json`。
- 公共写元数据强制包含 `request_id`、`idempotency_key`、`project_id`、`schema_version`、`expected_revision`。

输出：`CONTRACT_OK schemas=15 operations=12 write_metadata=5`。

## 未运行项

- InkOS Playwright E2E：根 `pnpm test` 不包含 `test:e2e`，本阶段没有另行启动浏览器。
- 真实 LLM/embedding/rerank：为避免网络、费用与非确定性，没有运行。
- 百万字性能与长时 soak：属于 Phase 3/9。
- 法律兼容性工具/律师审查：尚未执行。

