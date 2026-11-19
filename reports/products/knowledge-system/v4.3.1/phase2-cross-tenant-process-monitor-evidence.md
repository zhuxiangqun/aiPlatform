---
doc_type: Report
title: Phase 2 — process_monitor / state_changes tenant 证据（N09 Batch K11）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / process_monitor tenant（Batch K11）证据

> 实施权威：附录 N N09 partial 加深（K10 view/meta 之上：`state_changes.tenant_id` 物理列 + monitor 召回前过滤）。  
> **未宣称** process_instances 物理 tenant / OntologyEngine 写路径强制透传 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `state_changes` 含物理 `tenant_id` | pass | `_ensure_schema` CREATE/ALTER |
| `record_transition(..., tenant_id=)` 写入 | pass | `test_record_and_monitor_isolate_by_tenant` |
| process_monitor 按 tenant 过滤 | pass | 同测跨租户空 |
| monitor HTTP 注入 `resolve_request_tenant` | pass | `test_ontology_editor_tenant_k11.py` |
| 监控库与写入库路径统一 | pass | `process_monitor._db_path` → `state_history._db_path` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_process_monitor_tenant_k11.py \
  aiPlat-platform/tests/test_ontology_editor_tenant_k11.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Schema | `state_history._ensure_schema` + `idx_tenant_domain` |
| Write | `record_transition(..., tenant_id=)` |
| Read | `process_monitor.*(tenant_id=)` → Facade → HTTP |
| HTTP | `monitor_crud` + `resolve_request_tenant` |

## 明确未做

- `process_instances` / OntologyEngine tenant（见 Batch K12：`phase2-cross-tenant-process-instances-evidence.md`）
- auto_ontology_pipeline 强制非 default tenant
- metric/scoring/scenario/governance 旁路
- N09 / 附录 N 全量认证
