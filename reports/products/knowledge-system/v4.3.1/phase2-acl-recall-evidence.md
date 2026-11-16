---
doc_type: Report
title: Phase 2 — ACL 召回扩面证据（link.traverse / N07·N22 Batch C）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / ACL 召回扩面（Batch C）证据

> 实施权威：附录 N N07/N22 partial 加深。  
> **未宣称** Wiki/KB 全入口字段 ACL；仅 knowledge_pipeline 只读面（ObjectSet + link.traverse）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| deny 邻居不进 nodes/edges | pass | `test_entity_acl_drops_denied_neighbor` |
| deny 起点 → 空子图 | pass | `test_denied_start_returns_empty` |
| admin 可见 viewer deny | pass | `test_admin_sees_denied_for_viewer` |
| 字段脱敏 | pass | `test_field_acl_redacts_node` |
| 跨租户 0 泄漏（ACL 下） | pass | `test_cross_tenant_zero_leak_with_acl` |
| 既有 link.traverse 回归 | pass | `test_link_traverse_phase2` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_link_traverse_acl_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_link_traverse_phase2.py -v
# 预期：11 passed
```

实测（2026-11-16）：`11 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `link_traverse.traverse_links(..., role=)` → `check_entity_acl` / `redact_entity_fields` |
| Facade | `traverse_object_links(..., role=)` |
| Tool | `link.traverse` 透传 `role` |
| 既有 | ObjectSet `_apply_abox_acl`（W8） |

## 明确未做

- Wiki / KB / GraphRAG 全入口字段 ACL
- FactLedger 网关全量字段 ACL（本批以 link.traverse 为主）
- 附录 N 全量 / N07·N22 certified
