# 安装、升级与发布审计

总体：`FAIL`。Runtime standalone 在当前 Windows 开发机可构建和启动，但没有产品级一键 sidecar 接线、clean-machine installer 或已运行的 release workflow。

| 检查 | 状态 | 证据 |
|---|---|---|
| Windows Runtime standalone | PASS（开发机） | PyInstaller 6.21.0；EXE `--help` 和 loopback health 200 |
| Windows clean install | NOT VERIFIED | 未在无 Node/Python/缓存的 VM 执行 |
| macOS clean install | NOT VERIFIED | 无 macOS host/artifact |
| Linux clean install | NOT VERIFIED | 无 clean Linux install；远端 Python tests 失败 |
| Runtime 随产品安装 | FAIL | release workflow 只构建 Runtime；无 InkOS 产品 bundle |
| 用户无需 venv | PARTIAL | standalone 可行；产品未选择/启动它 |
| 一键启动 | FAIL | `StoryRuntimeProcessManager` 无生产实例化 |
| version/schema handshake | PASS（manager tests） | 未在产品 bootstrap 中发生 |
| token server-side/loopback | PASS | env token、proxy、host allowlist |
| offline core | PASS（Runtime） | soak 不调用 provider；全写作仍需 LLM/stub |
| upgrade + backup before schema change | PARTIAL | Runtime migration guard/snapshot 命令；完整产品 upgrade 未跑 |
| unsupported downgrade | PARTIAL | compatibility checks 有测试；package downgrade 未跑 |
| rollback | FAIL | post-cutover rollback 未实现；产品 upgrade rollback 未验证 |
| package checksum | PARTIAL | 未跟踪 workflow 会生成；本轮未产正式 release artifact checksum |
| source archive/SBOM | FAIL | 当前 release 未执行，repo 无生成 SBOM |
| NOTICE/third-party license | PARTIAL | NOTICE/InkOS LICENSE 存在；webnovel license 仅 workflow 下载 |
| AGPL/GPL provenance | FAIL | `UPSTREAM_PROVENANCE.yml` 标记 legal status provisional |
| release/known issues/migration/backup/DR docs | PARTIAL | 当前工作区有未跟踪文档，非发布基线 |

`release.yml` 本身未跟踪，也不依赖完整 CI 成功 job；只上传 Runtime 和 source/legal artifacts，不发布可启动的 InkOS+Runtime 产品。因此不能把 portable Runtime EXE 称为产品安装验收。

发布红线 9、16、17、18 已触发；clean install 相关项保持 NOT VERIFIED，不伪造跨平台 PASS。

