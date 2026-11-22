---
doc_type: Report
title: Phase 2 — ObjectSet ABox ACL 最小切片证据（W8 / H.1）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / ObjectSet ABox ACL（W8）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W8。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §H.1。  
> **未宣称**附录 N 全量符合；仅证明 ObjectSet 召回路径实例/字段 ACL + 跨租户负向。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 实例 deny 不进 items | pass | `test_entity_acl_filters_denied_instance` |
| 聚合不泄漏 deny 实例 | pass | 同上（count=1） |
| 字段脱敏（viewer） | pass | `test_field_acl_redacts_for_viewer` |
| admin 可见原字段 | pass | 同上 |
| 跨租户 0 泄漏 | pass | `test_cross_tenant_zero_leak` |
| 无 ACL 文件向后兼容 | pass | 既有 `test_object_set_phase2` 仍绿 |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_object_set_acl_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_object_set_phase2.py -v
# 预期：8 passed
```

实测（2026-11-16）：`8 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `object_set._apply_abox_acl` → `graph_abox_acl` |
| Facade | `query_object_set(..., role=)` |
| Tool | `object.query` / `object_set.aggregate` 透传 `role` |
| HTTP | `POST …/object-sets/query` ← `X-AIPLAT-ACTOR-ROLE` |

## 明确未做（后续）

- Wiki / KB / GraphRAG **全入口**字段 ACL（统一检索切片见 `phase2-wiki-kb-field-acl-evidence.md`）
- Scenario / Package（W9）
- 权限扩大负向套件以外的全量审计留存策略
- 附录 N 全量符合

> Batch C：`link.traverse` 已扩 ABox ACL — 见 `phase2-acl-recall-evidence.md`。  
> N07/N22 deepen：`sys_knowledge_retrieve` / KB / CRAG 字段 ACL — 见 `phase2-wiki-kb-field-acl-evidence.md`。
