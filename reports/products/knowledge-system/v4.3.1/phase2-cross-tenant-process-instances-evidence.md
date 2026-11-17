---
doc_type: Report
title: Phase 2 — process_instances / OntologyEngine tenant 证据（N09 Batch K12）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / process_instances + engine tenant（Batch K12）证据

> 实施权威：附录 N N09 partial 加深（K11 state_changes 之上：`process_instances.tenant_id` + OntologyEngine 写路径透传）。  
> **未宣称** auto_ontology_pipeline 强制非 default tenant / metric 旁路 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `process_instances` 含物理 `tenant_id` | pass | `_ensure_schema` CREATE/ALTER |
| `start_process(..., tenant_id=)` 写入 | pass | `test_process_instances_isolate_by_tenant` |
| get_process_status/get_bottlenecks 按 tenant 过滤 | pass | 同测跨租户空 |
| monitor HTTP 透传 tenant 到 process 端点 | pass | `test_ontology_editor_tenant_k12.py` |
| OntologyEngine/`record_transition` 带 tenant | pass | `tenant_id=self._tenant_id` + 单测 |
| 库路径对齐 state_history | pass | `process_orchestrator._db_path` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_process_instances_tenant_k12.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ontology_engine_tenant_k12.py \
  aiPlat-platform/tests/test_ontology_editor_tenant_k12.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Schema | `process_orchestrator._ensure_schema` |
| Write | `start_process` / `OntologyEngine` → `record_transition` |
| Read | Facade `get_process_status`/`get_bottlenecks` → HTTP |
| Factory | `load_engine(..., tenant_id=)` |

## 明确未做

- auto_ontology_pipeline ingest tenant（见 Batch K13：`phase2-cross-tenant-auto-ontology-pipeline-evidence.md`）
- metric/scoring/scenario/governance 旁路
- N09 / 附录 N 全量认证
