---
doc_type: Report
title: Phase 2 — diagnostics drift 身份绑定证据（N09 Batch K17）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / diagnostics drift identity（Batch K17）证据

> 实施权威：附录 N N09 partial 加深（K14 分库路径之上：drift HTTP 身份门）。  
> **未宣称** N09 certified（metric/scoring CRUD 见 K18）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| drift-status/rebuild 用 `actor_from_http` | pass | `test_drift_endpoints_source_use_actor_from_http` |
| status 取身份 tenant | pass | `test_get_drift_status_uses_identity_tenant` |
| rebuild 取身份 tenant | pass | `test_drift_rebuild_uses_identity_tenant` |
| 无 query `tenant_id` 旁路 | pass | 同上 source |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_diagnostics_drift_identity_k17.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| GET `/diagnostics/drift-status` | `actor_from_http(request)` → `StalenessMonitor(tenant_id=tid)` |
| POST `/diagnostics/drift-rebuild` | 同上 + `auto_ontology_pipeline_for_doc(..., tenant_id=tid)` |

## 明确未做

- metric/scoring/scenario/governance 旁路 CRUD → **K18 已加深**（本文件保留 K17 范围陈述）
- N09 / 附录 N 全量认证
