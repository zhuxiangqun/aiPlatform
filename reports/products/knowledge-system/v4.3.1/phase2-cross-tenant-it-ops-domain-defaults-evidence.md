---
doc_type: Report
title: Phase 2 — it-ops / data-gov domain 签名默认参数去硬编码证据（N09 Batch K46）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / it-ops + data-gov signature defaults（Batch K46）证据

> 实施权威：附录 N N09 partial 加深（`domain_id: str = "it-ops"|"data-gov"` → `DomainRouter.PLATFORM_IT_OPS_DOMAIN` / `PLATFORM_DATA_GOV_DOMAIN`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| PLATFORM_* + helpers | pass | `test_platform_constants_and_helpers` |
| 目标文件无字面量签名默认 | pass | `test_targets_use_platform_it_ops_or_data_gov` |
| 生产 it-ops/data-gov 签名默认清零 | pass | `test_production_it_ops_data_gov_signature_defaults_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_it_ops_domain_defaults_k46.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter SSOT | `PLATFORM_IT_OPS_DOMAIN` / `PLATFORM_DATA_GOV_DOMAIN` + `it_ops_domain()` / `data_gov_domain()` |
| org / FDE / facade 签名默认 | 上述常量 |

## 明确未做

- `domain_id: str = "aiplat-system"` → 见 Batch K47
- icebreaker_map 业务域键 / `tenant_id="default"`
- N09 / 附录 N 全量认证（certified 仍 false）
