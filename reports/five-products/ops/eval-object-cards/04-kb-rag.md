# 对象现状卡：KB/RAG

| 字段 | 填写内容 |
|---|---|
| 对象/场景 | 受控检索 fixture：hit 覆盖、expected IDs、groundedness/文本质量线索 |
| Owner / 日期 | 朱向群（已核实） / 2026-11-05 |
| 当前 runner/judge 及版本 | **Canonical**：package `kb_rag`（`ADR_CANONICAL_RUNNERS_V1.md`）。**SubjectAdapter**：`KbSubjectAdapter` + `kb.capability` 种子库（fixture hits/expected_ids，claim=false；**尚未**升一等 `OBJECT_TYPES`）。**Legacy 只读**：core `kb_eval_ops` / `rag_evaluator`（另一套维度，不可混称同一准确率）。UI Knowledge → `/eval?tab=knowledge`。 |
| 任务集、来源及现有样本量 | `payload.query` + `hits`/`docs` + 可选 `expected_ids`；无 hits → fail-closed。G2b 配额建议 KB/RAG=20。 |
| 当前实际测量维度 | hit_count、expected_ids 覆盖、groundedness（token-overlap）、text_quality/safety（P1 metrics）。core 路径另有 faithfulness 等。 |
| 判定方法（exact/rule/gold/human/LLM judge 等） | rule：有 `expected_ids` 则全部命中；否则 hits 非空即 ok。只读，不写 KB。 |
| 是否进入 composite（是/否/部分；说明） | 部分：package 指标可进 P1；core RAG 分数不可静默合并。同 `composite_version` 才可对比（#596/#604）。 |
| 失败处理（空回复/超时/缺 gold 等） | 无 hits → ok=false；expected_ids 未覆盖 → fail。 |
| 证据类型与等级 | EET：fixture / smoke；有 expected_ids 时接近 gold 对照；默认 `evidence_level=fixture`（#606）。 |
| Gate 资格（可进入/不可进入/有限条件；说明） | fixture 回归可入本地工程门；**不可**宣称 RAG 准确率或检索生产 SLO。 |
| 不能推出什么 / 已知限制 | 不是 live 检索质量认证；groundedness 为词项重合；与 core RAG 指标不可直接比。 |
