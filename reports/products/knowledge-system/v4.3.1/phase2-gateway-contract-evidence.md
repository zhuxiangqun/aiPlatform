---
doc_type: Report
title: Phase 2 — Gateway 查询契约证据（N06 Batch E2）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / Gateway 契约（Batch E2）证据

> 实施权威：附录 N N06 partial 加深（附录 F.1 最小切片）。  
> **未宣称** 统一 Query Gateway / N06 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| abstain 含 F.1 字段 + 空 answer/citations | pass | `test_abstain_has_f1_shape` |
| 命中含 citations + confidence_factors | pass | `test_hit_with_citations_contract` |
| 跨租户网关无泄漏 | pass | `test_cross_tenant_gateway_no_leak` |
| 缺字段 / 误标 certified 失败 | pass | `test_validate_rejects_missing_and_honesty` |
| 门槛门 certified 恒 false | pass | `test_gate_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_gateway_contract_phase2.py -v
# 预期：5 passed
```

实测（2026-11-16）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `query_facts_gateway` / `validate_gateway_response` / `evaluate_gateway_contract_gate` |
| Facade | `fact_ledger_query_gateway` + `validate_fact_gateway_response` + `evaluate_fact_gateway_contract_gate` |

## 明确未做

- 统一跨 Wiki/ObjectSet/Index 的 Query Gateway
- N06 / 附录 N 全量认证
