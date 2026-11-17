---
doc_type: Report
title: Phase 2 — staleness/diagnostics tenant KB 路径证据（N09 Batch K14）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / staleness + diagnostics tenant（Batch K14）证据

> 实施权威：附录 N N09 partial 加深（K13 auto_pipeline 之上：漂移扫描/重建按租户分库）。  
> **未宣称** metric/scoring 旁路 / N09 certified（cron 全租户见 K15）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `kb_sqlite_path_for_tenant` | pass | `staleness_monitor.py` |
| `StalenessMonitor(tenant_id=)` 选分库 | pass | `test_kb_sqlite_path_for_tenant` |
| auto_rebuild 透传 monitor tenant | pass | `test_staleness_source_uses_self_tenant` (`tenant_id=self._tenant_id`) |
| diagnostics drift-status/rebuild 接 tenant_id | pass | `test_diagnostics_source_wires_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_staleness_tenant_k14.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Path | `kb_sqlite_path_for_tenant(tenant_id)` |
| Monitor | `StalenessMonitor(tenant_id=)` → `_kb_db_path` |
| HTTP | `GET/POST …/diagnostics/drift-*?tenant_id=` |
| Rebuild | `auto_ontology_pipeline_for_doc(..., tenant_id=tid)` |

## 明确未做

- metric/scoring/scenario/governance 旁路 CRUD tenant
- server cron / system_health 全租户枚举扫描 → **K15 已加深**（本文件保留 K14 范围陈述）
- N09 / 附录 N 全量认证
