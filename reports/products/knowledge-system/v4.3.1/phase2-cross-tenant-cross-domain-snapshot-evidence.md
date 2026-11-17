---
doc_type: Report
title: Phase 2 — 跨域写边/publish snapshot 租户证据（N09 Batch K7）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / 跨域写边 + publish snapshot（Batch K7）证据

> 实施权威：附录 N N09 partial 加深（K6 图写入之上强制跨域边与 snapshot 分库）。  
> **未宣称** ontology_editor HTTP 全入口强制传 tenant / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 既有十二探针仍 pass | pass | `run_cross_tenant_isolation_suite` |
| 跨域 resolve 缺 tenant 拒绝 | pass | `cross_domain_resolve_tenant` |
| 跨域边仅本租户可见 | pass | 同上 |
| snapshot 按租户分库 | pass | 同上 + `list_snapshots` 幂等建表 |
| K-wave apply 透传 tenant | pass | `k_wave_arbit` → `resolve(tenant_id=)` |
| certified 恒 false | pass | gate / honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_cross_tenant_phase2.py -v
# 预期：2 passed（suite 13/13）
```

## 接线

| 入口 | 路径 |
|------|------|
| 跨域 | `CrossDomainResolver.resolve(..., tenant_id=)` 必填 |
| Publish | `publish_ontology_domain` / `list_rule_versions` / `rollback_rule_version` / `_save_rule_version(tenant_id=)` |
| Apply | `k_wave_arbit` `_ticket_tenant_id` 透传 |
| 套件 | `cross_domain_resolve_tenant` |

## 明确未做

- ontology_editor HTTP 强制从 JWT 注入 tenant（见 Batch K8：`phase2-cross-tenant-ontology-editor-http-evidence.md`）
- N09 / 附录 N 全量认证
