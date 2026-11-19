---
doc_type: Report
title: Phase 2 — staleness cron/health 全租户枚举证据（N09 Batch K15）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / staleness cron + system_health tenant（Batch K15）证据

> 实施权威：附录 N N09 partial 加深（K14 分库路径之上：cron/health 枚举全租户）。  
> **未宣称** metric/scoring 旁路 / N09 certified（garden/file/self_heal 见 K16）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `list_kb_tenant_ids` 发现分库 | pass | `test_list_kb_tenant_ids_discovers_dirs` |
| `aggregate_stale_summary` 聚合 | pass | `test_aggregate_stale_summary_uses_per_tenant_monitors` |
| governance cron 接 aggregate/rebuild | pass | `test_cron_and_health_source_wire_aggregate` |
| system_health 接 aggregate | pass | 同上 |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_staleness_cron_tenants_k15.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Enum | `list_kb_tenant_ids()` |
| Aggregate | `aggregate_stale_summary()` |
| Rebuild | `auto_rebuild_stale_tenants()` |
| Cron | `core/server.py` governance loop |
| Health | `system_health.py` staleness sub-score |

## 明确未做

- metric/scoring/scenario/governance 旁路 CRUD tenant
- auto_garden / sys_file / self_heal → **K16 已加深**（本文件保留 K15 范围陈述）
- N09 / 附录 N 全量认证
