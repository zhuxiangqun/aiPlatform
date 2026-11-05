# 对象现状卡：Session

| 字段 | 填写内容 |
|---|---|
| 对象/场景 | 有限多轮对话：v0=2–3 轮、v1=5–8 轮；先验轮次纯文本拼进下一轮 prompt |
| Owner / 日期 | 朱向群（已核实） / 2026-11-05 |
| 当前 runner/judge 及版本 | package `session_eval`（`app/worker/runners/session_eval.py` + `app/scoring/session.py`）；可选独立 LLM per turn。文档：`SESSION_V0.md` / `SESSION_V1.md`。 |
| 任务集、来源及现有样本量 | `payload.turns`/`messages` + profile；轮次不足 profile 下界 → fail。G2b 配额建议 Session=15。 |
| 当前实际测量维度 | turn_success_rate、session_pass、turns_n；每轮可附 prompt_eval 维度 / groundedness / efficiency。 |
| 判定方法（exact/rule/gold/human/LLM judge 等） | 每轮：有 expected → exact；无 expected → 非空 actual；整 session 聚合。无工具循环。 |
| 是否进入 composite（是/否/部分；说明） | 部分：session 维度 + 轮次 prompt 指标；不代表长程记忆/Agent。可比对仅限同 `composite_version`。 |
| 失败处理（空回复/超时/缺 gold 等） | 轮次不足 → ok=false；单轮 LLM 失败 → 该轮 fail，影响 rate。 |
| 证据类型与等级 | EET：fixture；有 expected 时 gold 对照；默认 `evidence_level=fixture`（无 gold 度量时）（#606）。 |
| Gate 资格（可进入/不可进入/有限条件；说明） | 可进本地多轮 fixture 回归；**不可**作长程上下文/记忆/生产对话认证。 |
| 不能推出什么 / 已知限制 | 无工具循环；先前轮次仅文本拼接；不足以验证压缩/冲突/截断/跨用户隔离。 |
