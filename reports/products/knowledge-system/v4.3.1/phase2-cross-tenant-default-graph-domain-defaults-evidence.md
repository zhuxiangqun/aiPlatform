---
doc_type: Report
title: Phase 2 — default graph domain 签名默认参数去硬编码证据（N09 Batch K45）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / default graph domain signature defaults（Batch K45）证据

> 实施权威：附录 N N09 partial 加深（`domain_id: str = "default"` → `DomainRouter.PLATFORM_DEFAULT_GRAPH_DOMAIN`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 目标文件用 PLATFORM_DEFAULT_GRAPH_DOMAIN | pass | `test_targets_use_platform_default_graph_domain` |
| 生产签名默认无 `"default"` domain 字面量 | pass | `test_production_default_domain_signature_defaults_empty` |
| tenant_id `"default"` 保留 | pass | `test_tenant_default_literal_still_allowed` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_default_graph_domain_defaults_k45.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| harness/API/syscall 签名默认 | `DomainRouter.PLATFORM_DEFAULT_GRAPH_DOMAIN` |

## 明确未做

- `domain_id: str = "it-ops"` / `"data-gov"` → 见 Batch K46；`aiplat-system` 等仍开放
- `tenant_id: str = "default"` / `collection_id: str = "default"`（非 ontology domain）
- icebreaker_map 业务域键
- N09 / 附录 N 全量认证（certified 仍 false）
