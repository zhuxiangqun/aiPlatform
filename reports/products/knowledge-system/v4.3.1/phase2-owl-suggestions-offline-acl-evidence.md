---
doc_type: Report
title: Phase 2 — suggestions OWL / offline_owl_review 身份透传（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / suggestions·offline OWL 字段 ACL（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 OWL 导出 A-Box ACL 之上。  
> **未宣称** N07/N22 certified / 字段 ACL 管理 UI / evolution_runner 热路径身份注入。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| suggestions 签名含 actor | pass | `test_export_suggestions_signature_has_actor` |
| description 脱敏 | pass | `test_redact_suggestion_description` / `test_export_suggestions_redacts_description` |
| offline 签名含 actor | pass | `test_offline_owl_review_signature_has_actor` |
| offline→export 透传 | pass | `test_offline_owl_review_passes_actor_to_export` |
| HTTP 接线 | pass | `test_router_learned_and_owl_review_wire_actor` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_owl_suggestions_offline_acl_phase2.py -v
# 预期：6 passed
```

实测（2026-11-19，`.venv` Python 3.11）：`6 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| suggestions | `export_suggestions_to_owl` / `write_suggestions_owl_file` → `_redact_suggestion_fields` |
| HTTP learned | `GET …/export/learned?actor_role=&actor_scopes=` |
| offline | `review_domain_owl_offline` → `export_to_owl_rdf(..., actor_*)` |
| Facade | `review_ontology_owl_offline` |
| HTTP review | `POST …/ontology/owl-review/{domain_id}` body 透传 actor |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 字段 ACL 管理 UI 大改
- `evolution_runner` 自动落盘路径注入运行时身份 → 见 `phase2-evolution-runner-acl-evidence.md`（本批 deepen）
