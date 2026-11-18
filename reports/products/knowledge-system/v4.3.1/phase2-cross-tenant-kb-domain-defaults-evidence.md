---
doc_type: Report
title: Phase 2 — KB domain 签名默认参数去硬编码证据（N09 Batch K44）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / KB domain signature defaults（Batch K44）证据

> 实施权威：附录 N N09 partial 加深（`domain_id: str = "ai-knowledge"` → `DomainRouter.PLATFORM_KB_DOMAIN`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 目标文件用 PLATFORM_KB_DOMAIN | pass | `test_targets_use_platform_kb_domain_default` |
| 生产签名默认无 ai-knowledge 字面量 | pass | `test_production_ai_knowledge_signature_defaults_empty` |
| FDE ask/export SSOT | pass | `test_fde_ask_and_export_use_ssot` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_kb_domain_defaults_k44.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| harness/API 签名默认 | `DomainRouter.PLATFORM_KB_DOMAIN` |
| DomainRouter 内部 fallback seed | `self.PLATFORM_KB_DOMAIN` / `PLATFORM_DEFAULT_GRAPH_DOMAIN` |
| FDE ask / OKF export | `PLATFORM_KB_DOMAIN` / `fde_kb_domain()` |

## 明确未做

- `domain_id: str = "default"` → 见 Batch K45；`"it-ops"` / `"data-gov"` 等其它业务域签名默认仍开放
- icebreaker_map 业务域键
- N09 / 附录 N 全量认证（certified 仍 false）
