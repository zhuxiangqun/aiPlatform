---
doc_type: Reference
---

# ADR：Prompt / KB 评测 canonical runner（P1a）

> **状态**：Accepted（2026-11-05）· 逾期默认条款按改善执行计划 P1a  
> **范围**：engineering 计分与本地 gate；不打开 `accuracy_claim`  
> **关联**：[P1_CANONICAL.md](./P1_CANONICAL.md) · 对象卡 Prompt/KB · [改善计划](../../../../reports/five-products/ops/EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md)

## 决策

| 对象 | Canonical（工程计分 / package composite） | Legacy（只读 / 管理面并存） |
|---|---|---|
| **Prompt** | `packages/aiplat-evaluation` `prompt_eval` runner + `prompt_eval_p1_bundle` | `core.apps.eval.service.prompt_eval_ops` + 管理端 Prompts tab 既有 API |
| **KB/RAG** | package `kb_rag` runner（fixture hits / expected_ids） | `core` `kb_eval_ops` / `rag_evaluator`（faithfulness 等另一套维度） |

1. **新任务、新报告、本地 gate、P1 composite** 必须以 package runner 路径为真相源。  
2. **Legacy core 路径不得静默写入 package composite**；UI/报告必须展示 `runner_id` + scoring schema/version。  
3. Legacy 在迁移完成前 **只读保留**（可继续 CRUD/跑历史），禁止新增第二套 engineering 权重。  
4. 跨路径比较默认标 **不可直接比较**（不同判分集合）。

## 后果

- Scorecard / Evidence / Gate 文案引用 package runner。  
- `text_quality` 自本 ADR 起在 package composite 中为 **report-only smoke**（见 composite policy `v1.1`），不得单独触发质量 gate。  
- Groundedness：仅在有 gold（expected/context/sources）时进入 metrics；仍为 token-overlap 启发，不得外推为事实认证。  
- 删除 legacy 需单独变更控制；本 ADR 不强制删代码。

## 非目标

≠ G2b accuracy · ≠ 生产拆分 · ≠ 统一 core RAG 与 package fixture 为同一数值
