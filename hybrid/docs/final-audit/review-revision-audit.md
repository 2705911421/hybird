# 审核与修订审计

总体：`PARTIAL`（7/8 级完成度）。Runtime 的 typed review 主链是真实实现，但产品级完整写作链仍被 surface/export 断裂阻止。

| 检查 | 状态 | 证据 |
|---|---|---|
| 正式 `ReviewArtifact` schema | PASS | `review-artifacts/v1` |
| Pydantic/JSON Schema/Zod 一致 | PASS | contract test + TS typecheck |
| 自由文本不能当 typed artifact | PASS | malformed/contract validation tests |
| CJK/emoji offset | PASS | `test_cjk_and_emoji_evidence_uses_unicode_code_point_offsets` |
| evidence hash 校验 | PASS | `reviews.py`、bad evidence test |
| revision 后 stale evidence | PASS | stale finding tests |
| blocking finding 阻止 commit | PASS | chapter validate/review gate tests |
| human decision 幂等 | PASS | Phase 5 E2E + unit test |
| stale revision decision 拒绝 | PASS | review tests |
| Reviser 不能直接写 authority | PASS | 最终仍需 Runtime validation/commit；无 Agent DB tool |
| revision 后 revalidation | PASS | Phase 5 E2E |
| 错误类型分层 | PASS | deterministic/fact/literary/human fields |
| duplicate finding 去重 | PASS | fingerprint dedupe test |
| reviewer 冲突保留 | PASS | disagreement requires human test |
| prompt injection 隔离 | PASS | 正文指令作为 hashed prose test |
| 旧 review JSON 第二 authority | PARTIAL | legacy adapter 仍存在，但 importer/adaptation 路径；未发现独立 authority write |

完整 typed 流程 `正文 -> blocking -> revision -> stale evidence -> re-review -> human decision -> commit`：`tests/integration/test_phase5_e2e.py` 1/1 PASS。

限制：该流程验证 Runtime/API，不证明 Studio 首页、章节列表、导出从同一 finalized chapter 读取；因此最终产品验收不能 PASS。

