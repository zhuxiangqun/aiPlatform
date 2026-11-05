# 对象现状卡：Arena

| 字段 | 填写内容 |
|---|---|
| 对象/场景 | 成对回答 A/B 比较（纯文本；禁 tools） |
| Owner / 日期 | 朱向群（已核实） / 2026-11-05 |
| 当前 runner/judge 及版本 | package `arena`（`app/worker/runners/arena.py` + `arena_p1_metrics`）。winner = **较长回答**（`judge_kind=length_heuristic`，`evidence_level=smoke`，`quality_gate_eligible=false`，`mode=arena_smoke_length`）。盲评脚手架 #597（rubric 冻结 + pack）；pilot≥30×2 **未开始**（见 `ARENA_BLIND_PILOT.md`）。 |
| 任务集、来源及现有样本量 | `response_a`/`response_b` + 可选 `prefer`/`expected_winner`；样本量由调用方。P1b 计划盲评 pilot 30–50 对（人侧排期）。现仅 fixture×3 供 pack smoke。 |
| 当前实际测量维度 | winner、text_quality（两侧）、safety；ok 在提供 prefer 时比对长度 winner。 |
| 判定方法（exact/rule/gold/human/LLM judge 等） | **heuristic**：`len(a)>=len(b) → a else b`；tools 标志 → `sandbox_required`。盲评 A/B/Tie 待 pilot。 |
| 是否进入 composite（是/否/部分；说明） | **否（正式质量）**；仅可作 smoke 工程观测；不得当用户偏好/质量胜负。`winner`/`text_quality` 为 report-only（#605）。 |
| 失败处理（空回复/超时/缺 gold 等） | 缺 a/b → ok=false；prefer 与长度 winner 不一致 → ok=false。 |
| 证据类型与等级 | **EET-1 smoke / heuristic**；runner 与 stamp 均强制 `evidence_level=smoke`（#606）。 |
| Gate 资格（可进入/不可进入/有限条件；说明） | **不可进入**发布质量 gate；长度 winner 须在 UI/报告降级为 smoke。 |
| 不能推出什么 / 已知限制 | 不能当作有效 judge、用户偏好或模型质量胜负；盲评 pilot 完成前保持 smoke。 |
