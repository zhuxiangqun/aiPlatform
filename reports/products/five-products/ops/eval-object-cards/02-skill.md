---
generated_at: 2026-11-11
doc_type: Report
---

# 对象现状卡：Skill

| 字段 | 填写内容 |
|---|---|
| 对象/场景 | Skill suite fixture：受控用例通过/失败比对（非 live 工具执行） |
| Owner / 日期 | 朱向群（已核实） / 2026-11-05 |
| 当前 runner/judge 及版本 | package `skill_suite`（`app/worker/runners/skill_suite.py`）；需 sandbox admit（docker `network=none` 或 microVM track）；`assert_skill_suite_fixture`。 |
| 任务集、来源及现有样本量 | `payload.cases` + 可选 `payload.results`/`actual_ok`；样本量=cases 长度，由调用方供给。无统一定义的全库 precision/recall 基线。 |
| 当前实际测量维度 | `pass`（passed/cases）、`cases`、`passed`；evidence：`tools_executed=false`、sandbox backend。 |
| 判定方法（exact/rule/gold/human/LLM judge 等） | rule：每 case `actual_ok`/`results[i].ok` 与 `expected_ok` 布尔相等；缺 result → 该 case fail-closed。 |
| 是否进入 composite（是/否/部分；说明） | 部分：可作为 quality 族 pass 输入；不单独定义 skill precision/recall 进 composite。写入 store 时 stamp `composite_version`（#598）。 |
| 失败处理（空回复/超时/缺 gold 等） | sandbox 未 admit → `sandbox_required`；wrap 失败 → ok=false；无 results 且无 actual_ok → case fail。失败样本可在 Reports 详情查看（#603）。 |
| 证据类型与等级 | EET：fixture / smoke（sandbox wrap ≠ 技能工具真实执行）；默认 `evidence_level=fixture`（#606）。 |
| Gate 资格（可进入/不可进入/有限条件；说明） | 可进本地 fixture 回归；**不可**作 live skill tools / microVM 执行认证。 |
| 不能推出什么 / 已知限制 | 不测量误触发/漏触发率；不执行真实 skill tools；Mac 主机无法解锁 live skill/microVM（见 G2b 仲裁笔记）。 |
