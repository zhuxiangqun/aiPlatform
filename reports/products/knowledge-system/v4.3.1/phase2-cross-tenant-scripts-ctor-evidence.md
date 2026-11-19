---
doc_type: Report
title: Phase 2 — scripts GraphIndex 直构租户证据（N09 Batch K35）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / scripts GraphIndex ctor（Batch K35）证据

> 实施权威：附录 N N09 partial 加深（scripts 侧 `GraphIndex(...)`）。  
> **未宣称** 域名硬编码消除 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 4 个脚本无裸 ctor | pass | `test_scripts_no_bare_graphindex_ctors` |
| CLI `--tenant` | pass | `test_scripts_cli_tenant_flags` |
| resolve 显式优先 | pass | `test_script_graph_tenant_prefers_explicit` |
| scaffold 模板 | pass | `test_scaffold_template_wires_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_scripts_ctor_tenant_k35.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| seed_lock_service_orders | `--tenant` → `_script_graph_tenant` → `GraphIndex(..., tenant_id=)` |
| benchmark_ontology / benchmark_traversal | 同上 |
| new_domain_scaffold 模板 | `tenant_id="default"` |

## 明确未做

- FDE/平台业务域名硬编码消除
- branch registry key 跨租户拆分 — 已由 K36 覆盖
- N09 / 附录 N 全量认证（certified 仍 false）
