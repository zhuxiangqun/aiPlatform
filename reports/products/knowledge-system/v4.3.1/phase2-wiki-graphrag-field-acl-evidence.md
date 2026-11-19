---
doc_type: Report
title: Phase 2 — Wiki 裸入口 / GraphRAG chunks 字段 ACL（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / Wiki·GraphRAG 字段 ACL（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `phase2-wiki-kb-field-acl-evidence.md` 之上。  
> **未宣称** N07/N22 certified / 导出全路径 / 附录 N 全量 / 字段 ACL 管理 UI。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| wiki 签名含 actor | pass | `test_wiki_retrieve_signature_has_actor_role` |
| `_sync_wiki_retrieve` 接线 | pass | `test_sync_wiki_retrieve_wires_acl_gate` / `test_sync_wiki_retrieve_calls_field_acl` |
| GraphRAG chunk ACL | pass | `test_graphrag_chunk_acl_redacts` |
| GraphRAG retrieve 透传 | pass | `test_graphrag_retrieve_applies_acl_on_chunks` |
| CRAG L0 早退接线 | pass | `test_crag_l0_wires_chunk_acl` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_wiki_graphrag_field_acl_phase2.py -v
# 预期：7 passed
```

实测（2026-11-19，`.venv` Python 3.11）：`7 passed`（连同既有 wiki-kb ACL 套件共 12 passed）。

## 接线

| 入口 | 路径 |
|------|------|
| 裸 Wiki | `sys_wiki_retrieve` / `_sync_wiki_retrieve` → `_apply_field_acl_to_results` |
| Wiki context | `sys_wiki_context` 透传 `actor_role` / `actor_scopes` |
| GraphRAG | `GraphRAGRetriever.retrieve` → `_apply_chunk_field_acl` |
| CRAG L0 | GraphRAG 早退前对 chunks 再跑字段 ACL |

## 明确未做

- 导出全路径（OKF / dump）字段 ACL → 见 `phase2-okf-export-field-acl-evidence.md`（本批 deepen）
- N07/N22 certified 或关闭 ADR 例外
- 字段 ACL 管理 UI 大改
- OWL/RDF 等其他导出格式全量字段 ACL
