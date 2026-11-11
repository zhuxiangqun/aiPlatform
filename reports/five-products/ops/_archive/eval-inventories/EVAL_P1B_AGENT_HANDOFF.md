# P1b 工程侧交接（agent 已交付 / 人侧待办）

> **日期**：2026-11-05
> **对照**：[EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04](../../EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md)

## 工程 closeout（报告轨）

**状态**：报告侧工程交付完成（#596–#606）。签认已收口项见下表。人侧劳动项工程已出卷/阻塞留档，总清单：EVAL_HUMAN_REMAINING_OPS_2026-11-05.md（历史链接失效）。

计划项「基线对比、维度回归、失败样本与元数据」对应交付：

| 计划要点 | 工程落点 |
|---|---|
| 基线对比 | `compare_reports` + UI 摘要（同 `composite_version`） |
| 维度回归 | `family_deltas` / `family_scores`；列表按 composite 过滤后对比 |
| 失败样本 | 详情失败表 + taxonomy；compare failures added/removed |
| 元数据 | runner/judge/dataset + `composite_version` + `evidence_level` |

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
| 列表 composite_version 过滤 | #604 | 筛同版本后对比快捷填入 |
| report_only 指标徽章 | #605 | 详情区分 family_scores vs report_only；弱代理不进门禁 |
| evidence_level 写入 meta | #606 | `infer_evidence_level`；详情展示；EET≠发布门禁 |
| 对象卡工程字段刷新 | （本批） | 七张对照 #596–#606；**owner 仍待核实签字** |

## 人侧状态

| 项 | 状态 | 材料 |
|---|---|---|
| **A1 本地联调** | ✅ **pass**（2026-11-05） | EVAL_A1_DEPLOY_SIGNOFF_local_20261105.md（历史链接失效） |
| **A1 生产/正式环境** | ☑ **blocked_not_released**（无正式 BASE） | 阻塞单（历史链接失效） · 母版（历史链接失效） |
| **EET 治理批准** | ✅ **Accept**（2026-11-05） | EVAL_EET_ACCEPT_2026-11-05.md（历史链接失效） · 映射 Accepted |
| **G2B-100 protocol 三方签认** | ✅ **SIGNED** · Holdout A | [SIGNED 留存](../../EVAL_G2B100_PROTOCOL_SIGNED_2026-11-05.md) · 母版（历史链接失效） |
| **G2b 31–100 双标/仲裁** | ✅ closeout + freeze 确认 + scoped attestation（n=100 · 0.72；**claim=false**） | closeout（历史链接失效） · `evidence/g2b_freeze_record.v1.json` · `g2b_accuracy_claim_attestation.v1.json` |
| **Arena pilot ≥30 对×2 盲评** | ✅ 双标+仲裁+result+QA（κ=0.8459；QA fail 已留档；smoke 未替换） | closeout（历史链接失效） · `evidence/arena_blind_qa_process.v1.json` |
| **对象卡 owner 核实** | ✅ **朱向群 ×7**（2026-11-05） | [EVAL_OBJECT_CARDS_OWNER_VERIFY.md](../../EVAL_OBJECT_CARDS_OWNER_VERIFY.md) |

## 诚实锁

`accuracy_claim=false` · length Arena = smoke · 跨 `composite_version` = 不可直接比较 · `process_split_authorized=false` · EET≠发布门禁等级
