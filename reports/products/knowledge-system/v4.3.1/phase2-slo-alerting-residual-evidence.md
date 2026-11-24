---
doc_type: Report
title: Phase 2 — SLO 告警候选显式 residual
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / SLO alerting residual

> 叠在 SLO 遥测接线与达标窗口之上。  
> **未宣称** Full unconditional / certified / 外部 pager 投递。  
> **`slo_telemetry_freeze` 保持 true**（不恢复默认 SLO wiring deepen）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 默认关闭告警候选 | pass | suite `slo_alert_unavailable` |
| opt-in 产出 misses_target 候选 | pass | suite `slo_alert_opt_in` |
| certified / n24_full / attainment_ok 恒 false | pass | suite / gate honesty |
| freeze 仍 true | pass | `n24-conformance-catalog.yaml` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_slo_alert_residual_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['slo_telemetry_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `evaluate_slo_alert_candidates` / suite/gate |
| Facade / HTTP | `evaluate_knowledge_slo_alert_candidates` + `POST …/slo/evaluate-alerts` |
| 实网开关 | `AIPLAT_KNOWLEDGE_SLO_ALERT=1` |

## 明确未做

- 外部 pager / 邮件 / webhook 投递
- Full unconditional / certified
- 恢复默认 SLO deepen mop
