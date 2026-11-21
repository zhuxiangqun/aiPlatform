---
doc_type: Report
title: Phase 2 — ABox 角色×动作轴证据（N07/N22 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N07/N22 角色×动作轴证据

> 实施权威：附录 N N07/N22 partial 加深。  
> **未宣称** 部署 RBAC/ACL 真源（N18）/ Wiki·KB 全入口 / N07·N22 certified。  
> 配置：`AIPLAT_ABOX_ROLE_ACTION_MATRIX`（JSON）+ 默认 viewer/analyst/admin；  
> `AIPLAT_ABOX_ROLE_ACTION_MATRIX_ENABLED=0` 可关闭。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 默认 viewer 只读 | pass | suite `viewer_read_ok` / `viewer_update_denied` |
| admin `*` | pass | suite `admin_star` |
| 任意角色扩展 | pass | suite `custom_role_*` |
| 未知角色拒绝 | pass | suite `unknown_role_denied` |
| `check_entity_acl` 接线 | pass | suite `check_entity_uses_matrix` |
| certified 恒 false | pass | suite `honesty_certified_false` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_role_action_matrix_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `load_role_action_matrix` / `role_action_allowed` / suite/gate |
| 实例门 | `check_entity_acl` 先过角色×动作轴 |
| Facade | `run_role_action_matrix_suite` / `evaluate_role_action_matrix_gate` |

## 明确未做

- 替换 `reference_policy.json` / 部署 RBAC 真源（N18）
- Wiki / KB / GraphRAG 全入口 ACL
- N07/N22 certified / 关闭 ADR 例外
