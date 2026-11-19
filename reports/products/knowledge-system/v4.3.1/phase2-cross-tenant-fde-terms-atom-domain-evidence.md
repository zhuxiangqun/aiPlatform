---
doc_type: Report
title: Phase 2 — FDE terms/atom/kb domain 去硬编码证据（N09 Batch K39）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / FDE terms·atom·kb domain（Batch K39）证据

> 实施权威：附录 N N09 partial 加深（`enterprise-terms` / `knowledge-atom` / `ai-knowledge` → DomainRouter helpers）。  
> **未宣称** 全域域名硬编码清零 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| platform FDE API 无裸域名 load | pass | `test_platform_fde_api_no_hardcoded_domain_loads` |
| DomainRouter helpers | pass | `test_domain_router_platform_domain_helpers` |
| fde_*_domain 委托 | pass | `test_fde_domain_helpers_delegate` |
| clarify_dialog tracking | pass | `test_clarify_dialog_uses_tracking_domain` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fde_terms_atom_domain_k39.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter | `terms_domain` / `knowledge_atom_domain` / `default_kb_domain` |
| `fde_terms_domain` / `fde_atom_domain` / `fde_kb_domain` | CoreFacade `get_domain_router()` |
| platform FDE GraphIndex.load | 上述 helpers + `fde_graph_tenant()` |
| clarify_dialog | `get_domain_router().tracking_domain()` |

## 明确未做

- harness 内 `knowledge-atom` 字面量 — 已由 K40 覆盖
- skills/registry `enterprise-terms` 字面量 — 已由 K40 覆盖
- N09 / 附录 N 全量认证（certified 仍 false）
