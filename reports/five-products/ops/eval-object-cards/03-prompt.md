# 对象现状卡：Prompt

| 字段 | 填写内容 |
|---|---|
| 对象/场景 | 单轮 prompt→回答：exact match、文本质量、groundedness、拒答、安全/PII、延迟成本 |
| Owner / 日期 | Evaluation owner（待核实） / 2026-11-04 |
| 当前 runner/judge 及版本 | **Canonical**：package `prompt_eval`（见 `ADR_CANONICAL_RUNNERS_V1.md`）。可选 `AIPLAT_EVAL_LLM` 独立 HTTP（拒 Central）。**Legacy 只读**：core `prompt_eval_ops`（不可静默并入 package composite）。 |
| 任务集、来源及现有样本量 | job payload：`prompt`/`expected`/`actual`/`context`/`sources`/`expect_refusal`；样本量由评测集决定。G2b 配额建议 Prompt=15。 |
| 当前实际测量维度 | exact_match、text_quality、groundedness（token-overlap 等）、safety/refusal、efficiency（latency/cost 若有 llm audit）。 |
| 判定方法（exact/rule/gold/human/LLM judge 等） | 默认 rule/exact（`actual==expected`）；无 expected 时非空即 ok；可选 live LLM 生成 actual。 |
| 是否进入 composite（是/否/部分；说明） | 部分：exact_match/gold-gated groundedness/safety/efficiency 可 scored；`text_quality` 自 v1.1 **report-only smoke**；ASR/accuracy/PII report-only。 |
| 失败处理（空回复/超时/缺 gold 等） | 无 actual 且无 LLM → ok=false；LLM 失败 → ok=false + audit；空 expected+空 actual → fail。 |
| 证据类型与等级 | fixture / gold（有 expected 时）/ smoke（仅 text_quality 启发）。 |
| Gate 资格（可进入/不可进入/有限条件；说明） | 有 gold 的 exact/回归可进**本地** gate；`text_quality` 为 composite report-only，**不可**单独触发质量 gate；≠ accuracy claim。 |
| 不能推出什么 / 已知限制 | 双 runner 口径分裂；text_quality≠语义质量；token-overlap groundedness≠事实支持。报告须标 runner/judge/version。 |
