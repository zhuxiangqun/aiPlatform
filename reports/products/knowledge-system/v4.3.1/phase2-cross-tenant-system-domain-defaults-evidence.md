---
doc_type: Report
title: Phase 2 — aiplat-system domain 签名默认参数去硬编码证据（N09 Batch K47）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / aiplat-system signature defaults（Batch K47）证据

> 实施权威：附录 N N09 partial 加深（`domain_id: str = "aiplat-system"` → `DomainRouter.system_domain()`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| PLATFORM_SYSTEM_DOMAIN + helper | pass | `test_platform_system_constant_and_helper` |
| wiki generate-domain 用 SSOT | pass | `test_wiki_generate_domain_uses_system_domain` |
| 生产 aiplat-system 签名默认清零 | pass | `test_production_aiplat_system_signature_defaults_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_system_domain_defaults_k47.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter SSOT | `PLATFORM_SYSTEM_DOMAIN` + `system_domain()` |
| `POST /wiki/generate-domain` | `domain_id: str = DomainRouter.system_domain()` |

## 明确未做

- `consultant_knowledge._DEFAULT_WIKI_COLLECTIONS` 中的 `"aiplat-system"` 集合名（wiki collection，非 domain_id 签名）
- icebreaker_map 业务域键 → 见 Batch K48；`tenant_id="default"` 仍开放
- N09 / 附录 N 全量认证（certified 仍 false）
