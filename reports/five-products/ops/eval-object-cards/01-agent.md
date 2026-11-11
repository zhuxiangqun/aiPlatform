---
doc_type: Report
---

# 对象现状卡：Agent

| 字段 | 填写内容 |
|---|---|
| 对象/场景 | Agent 任务完成 / 轨迹回放 / 管理端 Agents 面板观测 |
| Owner / 日期 | 朱向群（已核实） / 2026-11-05 |
| 当前 runner/judge 及版本 | **双路径**：(1) package `replay_trace`（`packages/aiplat-evaluation/app/worker/runners/replay_trace.py`）只读回放 `payload.trace`；(2) 管理端 `/eval?tab=agents` 内嵌 Diagnostics EvalDashboard → platform/core 历史 Agent 评估 API（Central `AgentEvalResult` / legacy_7dim）。无独立 package `agent` runner。 |
| 任务集、来源及现有样本量 | package：fixture/job payload 驱动，无固定公开 n；Central/UI：租户任务与历史 run，样本量运行时可变。G2b pack 中含 Agent/Skill 分层配额（见 G2B_100_PROTOCOL）。 |
| 当前实际测量维度 | `replay_trace`：pass、steps、latency（engineering）。Central：task/tool/traj/eff/recovery/safety/cost（**legacy_7dim，report-only**）。自定义 Agent scoring dimensions 可能存在且权重不一。 |
| 判定方法（exact/rule/gold/human/LLM judge 等） | rule/exact（trace.ok vs expected.ok）；Central 路径另有启发式/LLM 维度（以对应 runner 版本为准）。 |
| 是否进入 composite（是/否/部分；说明） | 部分：package P1 composite 可吞 `replay_trace` 族指标；Central legacy_7dim **禁止**当 engineering composite。报告须同 `composite_version` 才 comparable（#596）。 |
| 失败处理（空回复/超时/缺 gold 等） | 缺 trace → `ok=false`；expected.ok 不匹配 → fail。Central 路径：按各 API 超时/空产出规则（待核实具体端点）。 |
| 证据类型与等级 | EET：fixture（replay）/ smoke（Central UI 观测）；`meta.evidence_level` 由 `infer_evidence_level` 推断（#606）；≠ 发布门禁等级。 |
| Gate 资格（可进入/不可进入/有限条件；说明） | **不可**单独作为 accuracy 或外部 gate。本地 engineering 回归可用 `replay_trace`。 |
| 不能推出什么 / 已知限制 | 跨 Agent 总分不可比；legacy_7dim ≠ package P1；不代表生产 Agent 能力或工具循环质量。 |
