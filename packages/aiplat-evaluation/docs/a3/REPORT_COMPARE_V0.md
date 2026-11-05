# Report compare v0（P1b）

> **Honesty**：`accuracy_claim=false` · 仅工程分对比 · ≠ G2b  
> **SSOT**：`app/scoring/report_compare.py` · ADR：[ADR_SCORE_SCHEMA_VERSIONING_V1](./ADR_SCORE_SCHEMA_VERSIONING_V1.md)

## 规则

| 条件 | `comparable` | 用途 |
|---|---|---|
| 两侧 `policy.composite_version` 相同且非空 | `true` | 趋势 / 维度 delta / 失败样本差 |
| 版本缺失或不等 | `false` | 标「不可直接比较」；`raw_*` 仅调试 |

## API

`POST /api/platform/apps/eval/store/reports/compare`

```json
{ "baseline_id": "rpt_…", "candidate_id": "rpt_…" }
```

Cohost：`CoreFacade.eval_compare_reports` → package loader。  
Proxy：`AIPLAT_EVAL_SERVICE_URL` 转发 standalone。

管理端 Reports 对比区：先展示可读摘要（score/family/metric deltas + failures），原始 JSON 折叠。  
报告详情拉取：失败样本表（task_id / failure_category / score，最多 30）+ taxonomy 摘要，原始 JSON 折叠。  
Reports 列表可按 `composite_version` 客户端过滤；对比「快捷填入」使用当前过滤结果，便于选同版本基线/候选。  
报告详情：展示 `family_scores`（计入 composite）与 `report_only_metrics` 徽章（如 `text_quality`/`asr`）——后者不可进质量门禁、≠ accuracy。

## 写入侧（P1b stamp）

`create_report` 经 `ensure_report_scoring`：若 metrics 含已知工程指标且尚无 `composite_version`，自动挂上 `build_composite`（当前 `v1.1`）。已有版本不改写；纯运维字段（如 `phase`）不戳章 → 对比仍 incomparable。

同时 `ensure_report_meta` 将 `runner_id` / `judge_*` / `dataset_*` / `schema_version` 归入 `metrics.meta`（可显式传 `meta`），并把已有 `composite_version` 抄进 meta，供列表与对比追溯。

## 非目标

≠ 静默重算历史 · ≠ 打开 accuracy_claim · ≠ 跨版本门禁替换
