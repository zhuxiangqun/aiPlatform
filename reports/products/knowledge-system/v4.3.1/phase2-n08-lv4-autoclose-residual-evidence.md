---
doc_type: Report
title: Phase 2 — N08 有界 Lv4 auto-close 显式 residual
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N08 bounded Lv4 auto-close residual

> 叠在 Policy/Approval/Audit + Lv4 误报门 v2 之上。  
> **未宣称** 全量 Action Lv4 / N08 certified / Full unconditional。  
> **`n08_action_policy_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 默认关闭 | pass | suite `lv4_auto_close_unavailable` |
| opt-in 仅 low + Lv4 + FP 门 | pass | suite `lv4_auto_close_opt_in`（高风险仍拒绝） |
| certified / full_action_lv4 恒 false | pass | suite / gate honesty |
| freeze 仍 true | pass | `n24-conformance-catalog.yaml` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_lv4_bounded_auto_close_residual_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n08_action_policy_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `evaluate_bounded_lv4_auto_close` / suite/gate |
| Facade / HTTP | 同名 Facade + `/lv4-auto-close*` |
| 实网开关 | `AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE=1` |

## 明确未做

- 全量 Action Lv4 自动闭环产品化
- 中高风险动作自动放行
- N08 certified / 绕过 kill switch / require_approval
