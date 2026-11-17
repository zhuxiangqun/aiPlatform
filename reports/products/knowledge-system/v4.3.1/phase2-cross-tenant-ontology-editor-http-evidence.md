---
doc_type: Report
title: Phase 2 — ontology_editor HTTP tenant 注入证据（N09 Batch K8）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / ontology_editor HTTP tenant（Batch K8）证据

> 实施权威：附录 N N09 partial 加深（K7 snapshot API 之上接线 ontology_editor HTTP）。  
> **未宣称** 全量 ontology_editor CRUD / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `resolve_request_tenant` 经 `_resolve_identity` | pass | `auth/request_identity.py` |
| 裸 header spoof → default | pass | `test_resolve_request_tenant_ignores_spoofed_header` |
| publish / list_rule_versions 透传 tenant | pass | `test_publish_and_list_pass_resolved_tenant` |
| certified 恒 false | pass | honesty（本批不宣称 N09 certified） |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-platform/tests/test_ontology_editor_tenant_k8.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 身份 | `resolve_request_tenant(request)` → `_resolve_identity` |
| HTTP | `POST …/publish` / `GET …/rule-versions` → Facade `tenant_id=` |
| 测试 | `test_ontology_editor_tenant_k8.py` |

## 明确未做

- ontology_editor class/rollback tenant（见 Batch K9：`phase2-cross-tenant-ontology-editor-crud-evidence.md`）
- view/monitor 等旁路 CRUD / N09 / 附录 N 全量认证
