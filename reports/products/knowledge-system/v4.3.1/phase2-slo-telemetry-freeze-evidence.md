---
doc_type: Report
title: Phase 2 — SLO 遥测面冻结（Operational-sufficient）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
---

# Phase 2 / SLO 遥测面冻结

> 实施权威：白皮书 §14 / 认证槽位 `slo`；仿 N09 / N07 / N08 / N24 freeze。  
> **未宣称** 生产达标 / 告警闭环 / Full unconditional / 关闭 ADR 例外行。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| catalog `slo_telemetry_freeze: true` | pass | `n24-conformance-catalog.yaml` |
| conformance pack / core_ready 透传 | pass | `build_conformance_pack` / `evaluate_core_ready_gate` |
| 测试断言 freeze | pass | `test_core_cert_path_phase2` |
| ADR 期限「遥测足够」 | pass | `phase2-exception-adr.md` SLO |
| `certified` / 达标宣称恒 false | pass | honesty（wiring≠attainment） |

## 命令

```bash
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['slo_telemetry_freeze'] is True"
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_core_cert_path_phase2.py -v
```

## 接线

| 入口 | 路径 |
|------|------|
| Catalog | `slo_telemetry_freeze` / `slo_telemetry_note` |
| Pack/Gate | `conformance_pack.py` 透传布尔旗 |

## 明确未做

- 生产达标宣称 / Grafana / PagerDuty
- ingest / object-sync / 索引重建 SLI 默认 deepen
- 用接线冒充 Full unconditional
