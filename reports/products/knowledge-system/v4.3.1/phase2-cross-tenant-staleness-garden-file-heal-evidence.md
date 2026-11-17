---
doc_type: Report
title: Phase 2 — staleness garden/file/self_heal 租户扫描证据（N09 Batch K16）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / garden + sys_file + self_heal tenant（Batch K16）证据

> 实施权威：附录 N N09 partial 加深（K15 cron/health 之上：残留调用面）。  
> **未宣称** metric/scoring 旁路 / N09 certified（diagnostics 身份绑定见 K17）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| sys_file 高风险写按 tenant 扫 | pass | `test_file_source_wires_tenant_scan` |
| AutoGarden 入口按租户扫 | pass | `test_garden_source_wires_tenant_scan` + `test_garden_scan_uses_explicit_tenant` |
| SelfHeal stale_mark 按租户扫 | pass | `test_self_heal_source_wires_tenant_scan` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_staleness_garden_file_heal_k16.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| sys_file_write | `_check_hallucination_on_write(..., trace_context=)` → `list_kb_tenant_ids` / `StalenessMonitor(tenant_id=)` |
| AutoGarden | `run(tenant_id=)` → `_scan_staleness_tenants` |
| SelfHealGate | `stale_mark` + `data.tenant_id` → 分库扫描 |

## 明确未做

- metric/scoring/scenario/governance 旁路 CRUD tenant
- diagnostics drift HTTP 身份绑定 → **K17 已加深**（本文件保留 K16 范围陈述）
- N09 / 附录 N 全量认证
