---
doc_type: Report
title: Phase 2 — OKF 导出写盘字段 ACL（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / OKF 导出字段 ACL（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 Wiki/GraphRAG 字段 ACL 之上。  
> **未宣称** N07/N22 certified / 字段 ACL 管理 UI / 附录 N 全量。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| export 签名含 actor | pass | `test_export_signature_has_actor_role` |
| 元数据脱敏 | pass | `test_redact_entity_fields_viewer` |
| admin 旁路 | pass | `test_redact_entity_fields_admin_bypass` |
| body 写盘前脱敏 | pass | `test_build_body_redacts_metadata` |
| FDE 透传 | pass | `test_fde_export_okf_wires_actor` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_okf_export_field_acl_phase2.py -v
# 预期：5 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Core | `OKFExporter.export` → `_build_body` → `_redact_entity_fields` |
| HTTP | `POST …/fde/knowledge/export-okf` 透传 `actor_role` / `actor_scopes` / `collection_id` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 字段 ACL 管理 UI 大改
- OWL/RDF 等其他导出格式全量字段 ACL
