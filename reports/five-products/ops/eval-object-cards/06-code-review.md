# 对象现状卡：Code Review

| 字段 | 填写内容 |
|---|---|
| 对象/场景 | Gold finding 集合匹配（静态/半静态；无 sandbox 工具跑审查） |
| Owner / 日期 | Evaluation owner（待核实） / 2026-11-05（工程刷新；owner 未签） |
| 当前 runner/judge 及版本 | package `code_review_gold`（`app/worker/runners/code_review_gold.py`）。另有平台 Code Review Gold API / match-only 脚本（`scripts/eval_code_review_gold.py` 等）— 报告须标路径。 |
| 任务集、来源及现有样本量 | `payload.findings` vs `payload.gold`；缺 gold → fail。workspace seeds / gold 目录可提供固定集。G2b 配额建议 Code Review=15；P0 切片需最小 n。 |
| 当前实际测量维度 | exact set match、coverage、P1 metrics（precision/recall/F1 等在 semantics 层按实现）；P0 recall 在更完整 gold 路径中。 |
| 判定方法（exact/rule/gold/human/LLM judge 等） | gold：`sorted(str(findings)) == sorted(str(gold))` 精确集合相等。 |
| 是否进入 composite（是/否/部分；说明） | 部分：engineering 匹配分可进；≠ 生产审查能力总分。store 报告 stamp meta + composite（#598/#600）。 |
| 失败处理（空回复/超时/缺 gold 等） | 无 gold → ok=false；集合不等 → fail。 |
| 证据类型与等级 | EET：gold / fixture；runner 名含 `gold` → 默认 `evidence_level=gold`（#606）。 |
| Gate 资格（可进入/不可进入/有限条件；说明） | gold match-only 可进**本地回归**；P0 切片低于预注册最小 n 时 report-only；≠ 真实仓库端到端审查认证。 |
| 不能推出什么 / 已知限制 | fixture/match-only ≠ 真实 codebase autoreview E2E；字符串化集合相等可能过严/过宽。 |
