---
doc_type: Report
title: Phase 2 — Wiki/KB 字段 ACL 加深（N07/N22 residual）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / Wiki/KB 字段 ACL（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；复用 `field_level_security` + `sys_knowledge_retrieve` 统一入口。  
> **未宣称** N07/N22 certified / Wiki·KB·GraphRAG·HyDE 全入口 / 附录 N 全量。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| viewer 字段脱敏 | pass | `test_field_acl_redacts_for_viewer` |
| admin 旁路 | pass | `test_field_acl_admin_bypass` |
| 无 perm 文件兼容 | pass | `test_field_acl_no_perm_file_passthrough` |
| retrieve 接线条件 | pass | `test_retrieve_gate_skips_when_no_identity` |
| KB 签名含 actor_role | pass | `test_kb_retrieve_signature_has_actor_role` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_wiki_kb_field_acl_phase2.py -v
# 预期：5 passed
```

实测（2026-11-19，`.venv` Python 3.11）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `retrieval._apply_field_acl_to_results` → `field_level_security` |
| 统一检索 | `sys_knowledge_retrieve(..., actor_role=, actor_scopes=)` |
| KB 直检 | `sys_kb_retrieve(..., actor_role=)` |
| CRAG | `sys_crag_retrieve` 透传；Level2 组装前脱敏 + 返回 citations 脱敏 |
| materials_chat | `options`/`run_context` → actor_role/scopes |

## 明确未做

- 裸 `sys_wiki_retrieve` / GraphRAG 子图单独入口 / 导出全路径
- N07/N22 certified 或关闭 ADR 例外
- 字段 ACL 管理 UI 大改
