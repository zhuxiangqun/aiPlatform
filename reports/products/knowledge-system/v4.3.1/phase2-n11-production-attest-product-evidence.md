---
doc_type: Report
title: Phase 2 — N11/N14 生产切写就绪产品面第一刀
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N11 production attest product surface (slice-1)

> 显式产品面开刀：默认可用生产切写就绪回执（无 residual env）。  
> **`prod_attest_product_surface=true`**；仍须作业级授权 + 对账干净。  
> **未宣称** N11/N14 certified / `production_cutover_certified` / 自动切写。  
> **`n11_n14_migration_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无 residual env 即可评估 | pass | suite `prod_attest_product_eval` |
| 未授权作业诚实阻断 | pass | suite `prod_attest_product_blocked_unauthorized` |
| certified / production_cutover_certified 恒 false | pass | suite / gate honesty |
| 管理端薄面板挂载 | pass | `ProductionAttestPanel` → `/knowledge-migrations/product*` |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_production_attest_product_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n11_n14_migration_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `attest_production_cutover_readiness_product` / suite·gate |
| Facade / HTTP | 同名 Facade + `/knowledge-migrations/product/*` |
| UI | `ProductionAttestPanel` |

## 明确未做

- 生产切写认证 / `production_cutover_certified=true`
- 自动切写 / 绕过作业级 token
- N11/N14 certified
- 关闭 residual opt-in 路径（仍保留）
