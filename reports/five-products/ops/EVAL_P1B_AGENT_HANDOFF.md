# P1b 工程侧交接（agent 已交付 / 人侧待办）

> **日期**：2026-11-05  
> **对照**：[EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04](./EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md)

## 已合入（工程）

| 项 | PR | 说明 |
|---|---|---|
| 报告对比（同 `composite_version`） | #596 | `compare_reports` + `/store/reports/compare` + Reports UI |
| Arena 盲评 rubric + pack 脚手架 | #597 | 冻结 rubric；打乱左右/去模型名；fixture≠pilot 完成 |
| 报告写入 stamp `composite_version` | #598 | 已知工程指标自动挂 `build_composite` v1.1 |
| 报告 meta（runner/judge/dataset）+ 列表展示 | #600 | `ensure_report_meta`；列表显示 meta 摘要 |
| runner/gate/judge 写入 meta | #601 | `enrich_runner_result` + gate/judge `create_report(meta=…)` |
| 对比结果摘要 UI | #602 | deltas/failures 摘要；JSON 折叠 |
| 报告详情失败样本 UI | #603 | task_id/category/score 表 + taxonomy；JSON 折叠 |
| 列表 composite_version 过滤 | （本批） | 筛同版本后对比快捷填入 |

## 人侧仍 open（工程无法代签）

| 项 | 阻塞 |
|---|---|
| **A1 部署签认** | 目标环境构建 ID、旧 `/diagnostics/eval` `/platform/kb/eval` 须 404、CDN 缓存 · **检查表**：[EVAL_A1_DEPLOY_SIGNOFF.md](./EVAL_A1_DEPLOY_SIGNOFF.md) |
| **EET 治理批准** | `EVAL_EVIDENCE_LEVEL_MAP_V1` Proposed → Accept |
| **G2B-100 protocol 三方签认** | 签后才可开 31–100 确认性双标 |
| **G2b 31–100 双标/仲裁** | ≥2 标注者；预算 25–30 人时 |
| **Arena pilot ≥30 对×2 盲评** | 排期评审；现仅 fixture×3 供 pack smoke |
| **对象卡 owner 核实** | `eval-object-cards/` 七张 |

## 诚实锁

`accuracy_claim=false` · length Arena = smoke · 跨 `composite_version` = 不可直接比较 · `process_split_authorized=false`
