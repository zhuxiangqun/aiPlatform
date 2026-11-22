---
doc_type: Report
title: Phase 2 — 部署侧 RBAC 真源证据（N18 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N18 部署侧 RBAC 证据

> 实施权威：附录 N N18 deepen（替换 reference_policy 为部署权威）。  
> **未宣称** N18 certified / 召回过滤·聚合·导出·缓存全路径 / 附录 N 全量符合。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 权威源非 reference_policy | pass | suite `source_not_reference_file` |
| 同租户 allow/deny | pass | suite `same_tenant_*` |
| 跨租户 deny | pass | suite `cross_tenant_deny` |
| approval 结果 | pass | suite `approval_outcome` |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_deployed_rbac_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `load_deployed_policy` / `evaluate_permission` / suite/gate |
| Facade / HTTP | 同名 + `/fde/deployed-rbac*` |
| 配置 | `AIPLAT_DEPLOYED_RBAC_POLICY` / `_PATH` / `AIPLAT_HOME/rbac/deployed_policy.json` |

## 明确未做

- 召回时过滤 / 聚合 / 导出 / 缓存全路径强制经本源
- 删除标准包 `reference_policy.json`（仍为参考资产）
- N18 certified / 关闭 ADR 例外冒充签字
