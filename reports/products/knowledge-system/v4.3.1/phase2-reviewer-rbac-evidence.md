---
doc_type: Report
title: Phase 2 — Fact publish reviewer 角色门证据（N04/N12 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N04/N12 reviewer 角色门证据

> 实施权威：附录 N N04/N12 partial 加深。  
> **未宣称** 部署侧 RBAC/ACL 真源替换（N18）/ N04/N12 certified；仅配置驱动
> publish 角色门（上游注入 `role`，不从 actor 名推断）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 允许角色可 publish | pass | suite `publisher_role_allowed` |
| 错误角色拒绝 | pass | suite `wrong_role_denied` |
| 空角色拒绝 | pass | suite `empty_role_denied` |
| certified 恒 false | pass | suite `honesty_certified_false` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_reviewer_rbac_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `assert_reviewer_role` / `run_reviewer_rbac_suite` / `evaluate_reviewer_rbac_gate` |
| 转换 | `transition_fact_review(..., role=)` |
| Facade / HTTP | 同名 + `FactTransitionBody.role` |
| 配置 | `AIPLAT_FACT_REVIEWER_RBAC` / `AIPLAT_FACT_REVIEWER_ROLES` |

## 明确未做

- 部署侧 RBAC 真源 deepen 见 `phase2-deployed-rbac-evidence.md`（本 reviewer 门≠N18 全路径）
- 任意角色×动作轴产品化
- N04/N12 certified / 关闭 ADR 例外
