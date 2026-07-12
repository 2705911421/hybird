# ADR-006：RAG 与精确查询的适用边界

- 状态：Accepted
- 日期：2026-07-11

## 背景

人物属性、关系、时间线和伏笔状态需要确定答案；语义相似场景、文风样本和遥远章节召回适合 RAG。向量检索可能失效或缺少外部 key。

## 决策

事实问题先走 SQL exact query；RAG 只补充非规范文本与候选 evidence。Context query 显式区分 `authoritative_facts`、`retrieval_candidates` 和 `untrusted_materials`。

## 后果

- 无 embedding 时核心写作/提交仍可用。
- RAG 索引可删除重建，不参与 revision CAS。
- 模型不得用 RAG 候选覆盖矛盾的权威事实。

