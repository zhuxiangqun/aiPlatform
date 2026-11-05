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

## 非目标

≠ 静默重算历史 · ≠ 打开 accuracy_claim · ≠ 跨版本门禁替换
