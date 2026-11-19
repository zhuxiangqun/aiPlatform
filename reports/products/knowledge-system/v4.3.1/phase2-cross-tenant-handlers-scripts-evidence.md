---
doc_type: Report
title: Phase 2 — custom_handlers / seed scripts GraphIndex 租户证据（N09 Batch K33）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / handlers · scripts tenant（Batch K33）证据

> 实施权威：附录 N N09 partial 加深（custom_handlers + quick_seed / scaffold）。  
> **未宣称** 域名硬编码消除 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| custom_handlers 5 处 load tenant | pass | `test_custom_handlers_source_wires_tenant` |
| quick_seed `--tenant` + load | pass | `test_quick_seed_source_wires_tenant` |
| handler params 优先 | pass | `test_handler_graph_tenant_prefers_params` |
| seed tenant 优先 | pass | `test_seed_tenant_prefers_explicit` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_handlers_scripts_tenant_k33.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| custom_handlers | `_handler_graph_tenant(params)` → CoreFacade `resolve_graph_tenant` |
| quick_seed | `--tenant` / `_seed_tenant` → `GraphIndex.load(..., tenant_id=)` |
| new_domain_scaffold 模板 | `tenant_id="default"` |
| graph_traversal 文档示例 | 补 tenant 示例（非执行代码） |

## 明确未做

- FDE/平台业务域名硬编码（`fde-delivery` 等）消除
- GraphIndex 直构 / branch DB 前缀（见 K34）
- N09 / 附录 N 全量认证（certified 仍 false）
