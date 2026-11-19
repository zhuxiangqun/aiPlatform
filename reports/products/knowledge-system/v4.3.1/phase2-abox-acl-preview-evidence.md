---
doc_type: Report
title: Phase 2 — ABox ACL preview-as-role（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL 按角色预览（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 ABox DELETE 之上。  
> **未宣称** N07/N22 certified / H.1 condition 策略编辑器 / 全量权限产品。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| preview deny/redact | pass | `test_preview_abox_acl_deny_and_redact` |
| Facade + HTTP | pass | `test_preview_facade_and_route` |
| 薄 UI 接线 | pass | `test_abox_panel_wires_preview` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_preview_phase2.py -v
# 实测 2026-11-20：3 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `preview_abox_acl` → allow + redact |
| Facade | `preview_graph_abox_acl` |
| HTTP | `POST …/fde/graph/acl/{domain}/preview` |
| UI | `AboxAclPanel` 「按角色预览」 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- H.1 `condition` 最小匹配 → 见 `phase2-abox-acl-condition-evidence.md`
- 完整策略编辑器 / 批量导入 / 审批流权限产品
