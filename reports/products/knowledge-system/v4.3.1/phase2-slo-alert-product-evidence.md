---
doc_type: Report
title: Phase 2 — SLO 告警候选产品面第一刀
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / SLO alert product surface (slice-1)

> 显式产品面开刀：默认可用有界告警候选（无 residual env）。  
> **`slo_alert_product_surface=true`**；仍仅结构化候选，不投递 pager。  
> **未宣称** Full unconditional / certified / `attainment_ok`。  
> **`slo_telemetry_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无 residual env 即可出候选 | pass | suite `slo_alert_product_eval` |
| residual 无 env 仍 unavailable | pass | suite `slo_alert_product_unavailable` |
| certified / attainment_ok 恒 false | pass | suite / gate honesty |
| 管理端薄面板挂载 | pass | `SloAlertPanel` → `/slo/product*` |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_slo_alert_product_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['slo_telemetry_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `evaluate_slo_alert_candidates_product` / suite·gate |
| Facade / HTTP | 同名 Facade + `/slo/product/*` |
| UI | `SloAlertPanel` |

## 明确未做

- 外部 pager / 邮件 / webhook 投递
- Full unconditional / certified / attainment_ok=true
- 关闭 residual opt-in 路径（仍保留）
- 恢复默认 SLO deepen mop
