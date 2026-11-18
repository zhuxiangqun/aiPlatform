---
doc_type: Report
title: Phase 2 — ontology branch registry 租户键证据（N09 Batch K36）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / branch registry tenant（Batch K36）证据

> 实施权威：附录 N N09 partial 加深（`branches.json` registry key 租户隔离）。  
> **未宣称** 域名硬编码消除 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 租户键格式 | pass | `test_branch_key_tenant_formats` |
| default 读旧键 | pass | `test_find_branch_entry_legacy_default` |
| list 跨租户隔离 | pass | `test_list_branches_isolates_tenants` |
| FDE list 透传 | pass | `test_fde_list_branches_passes_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_branch_registry_tenant_k36.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| `_branch_key` | default=`domain::branch`；非 default=`tenant::domain::branch` |
| fork/delete/get/commit/list/merge | 读写走租户键；default 可读 legacy |
| FDE `/branches/{domain_id}` | `tenant_id=fde_graph_tenant()` |

## 明确未做

- 分支 YAML 路径租户前缀 — 已由 K37 覆盖
- FDE/平台业务域名硬编码消除
- N09 / 附录 N 全量认证（certified 仍 false）
