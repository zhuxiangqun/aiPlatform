---
doc_type: Report
title: Phase 2 — N08 有界 Lv4 auto-close 产品面第一刀
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N08 bounded Lv4 auto-close product surface (slice-1)

> 显式产品面开刀：默认可用有界 Lv4 auto-close 评估（无 residual env）。  
> **`lv4_product_surface=true`**；仍仅 low 风险 + 误报门 v2。  
> **未宣称** N08 certified / `full_action_lv4` / 中高风险放行。  
> **`n08_action_policy_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无 residual env 即可评估 | pass | suite `lv4_auto_close_product_eval` |
| 高风险仍拒绝 | pass | suite `lv4_auto_close_product_high_risk_denied` |
| certified / full_action_lv4 恒 false | pass | suite / gate honesty |
| 管理端薄面板挂载 | pass | `Lv4AutoClosePanel` → `/lv4-auto-close/product*` |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_lv4_auto_close_product_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n08_action_policy_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `evaluate_bounded_lv4_auto_close_product` / suite·gate |
| Facade / HTTP | 同名 Facade + `/lv4-auto-close/product*` |
| UI | `Lv4AutoClosePanel` |

## 明确未做

- 全量 Action Lv4 自动闭环产品化（`full_action_lv4`）
- 中高风险动作自动放行
- N08 certified / 绕过 kill switch / require_approval
- 关闭 residual opt-in 路径（仍保留）
