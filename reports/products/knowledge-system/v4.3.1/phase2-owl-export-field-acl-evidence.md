---
doc_type: Report
title: Phase 2 — OWL/RDF 导出 A-Box 字段 ACL（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / OWL·RDF 导出字段 ACL（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 OKF 导出字段 ACL 之上。  
> **未宣称** N07/N22 certified / 字段 ACL 管理 UI / suggestions OWL 全路径。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| export 签名含 actor | pass | `test_export_to_owl_rdf_signature_has_actor` |
| A-Box 字面量脱敏 | pass | `test_redact_owl_abox_literal` |
| admin 旁路 | pass | `test_redact_owl_abox_admin_bypass` |
| 无身份兼容 | pass | `test_redact_owl_abox_no_identity_passthrough` |
| HTTP 透传 | pass | `test_router_export_wires_actor` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_owl_export_field_acl_phase2.py -v
# 预期：5 passed
```

实测（2026-11-19，`.venv` Python 3.11）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| Core | `export_to_owl_rdf` → `_redact_owl_abox_triples` |
| HTTP | `GET …/wiki-ontology-export/export?actor_role=&actor_scopes=` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 字段 ACL 管理 UI 大改
- `export/learned` suggestions OWL / offline_owl_review 身份透传 → 见 `phase2-owl-suggestions-offline-acl-evidence.md`
