---
doc_type: Report
title: Phase 2 — Action Policy/Approval/Audit 证据（N08 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N08 Policy·Approval·Audit 证据

> 实施权威：附录 N N08 partial 加深。  
> **未宣称** N08 certified / Lv4 误报门全量重设计。  
> 加深：`AIPLAT_ACTION_KILL_SWITCH`；`require_approval` 无 threshold 时强制入队（禁 silent 直跑）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| kill switch 阻断 | pass | suite `kill_switch_blocks` |
| 裸 bypass 拒绝 | pass | suite `bypass_forbidden` |
| Policy 拒 + 审计 | pass | suite `policy_denied*` |
| require_approval 入队 | pass | suite `approval_enqueued` |
| certified 恒 false | pass | suite `honesty_certified_false` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_action_policy_audit_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 急停 | `action_kill_switch_active` → `execute` 早返回 `kill_switch` |
| 审批 | `require_approval` 且无 threshold → `_enqueue_approval` |
| Facade | `run_action_policy_audit_suite` / `evaluate_action_policy_audit_gate` |

## 明确未做

- Lv4 误报门全量重设计
- N08 certified / 关闭 ADR 例外
