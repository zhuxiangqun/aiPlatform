---
doc_type: Report
title: Phase 2 — N08 有界 Lv4 auto-close 产品面第二刀（medium + 审批/急停）
status: active
authority: supporting
measured_at: 2026-11-25
pilot_domain: lock-service
---

# Phase 2 / N08 bounded Lv4 auto-close product surface (slice-2)

> 实施权威：附录 N N08 产品面第二刀。  
> **默认可用**：low 直评；medium 须 `approval_attested` + `kill_switch_clear`，且 `action_kill_switch_active()` 为假。  
> **诚实锁**：`lv4_product_surface=true` / `lv4_medium_approval_product=true`；`full_action_lv4` / `certified` 恒 false。  
> **`n08_action_policy_freeze` 保持 true**。  
> **未宣称** full_action_lv4 / high·critical 放行 / N08 certified / 关闭 ADR 例外。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 产品 low 可过 | pass | suite `lv4_auto_close_product_eval` |
| 高风险仍拒绝 | pass | suite `lv4_auto_close_product_high_risk_denied` |
| medium 无审批拒绝 | pass | suite `lv4_auto_close_product_medium_denied_without_approval` |
| medium+门可过 | pass | suite `lv4_auto_close_product_medium_ok_with_gates` |
| 急停启用拒绝 | pass | suite `lv4_auto_close_product_medium_kill_switch_active` |
| certified / full_action_lv4 恒 false | pass | suite / gate honesty |
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
| 核心 | `evaluate_bounded_lv4_auto_close_product`（+ medium 门）/ suite·gate |
| Facade / HTTP | 同名 Facade + `/lv4-auto-close/product*`（`approval_attested`/`kill_switch_clear`） |
| UI | `Lv4AutoClosePanel` |

## 明确未做

- 全量 Action Lv4 自动闭环产品化（`full_action_lv4`）
- high/critical 风险自动放行
- 绕过 ActionRegistry 生产执行 / kill switch / require_approval
- N08 certified / 翻 `n08_action_policy_freeze`
