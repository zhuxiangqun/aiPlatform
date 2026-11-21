---
doc_type: Report
title: Phase 2 — Unified Audit UI materialize 加深证据（N24 Batch J13）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / Unified Audit UI Materialize（Batch J13）证据

> 实施权威：附录 N N24 partial 加深（管理端统一审计面板 materialize + 写总线只读列表）。  
> **未宣称** N24 certified / 全量写总线运维台。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| materialize 按钮 → POST `/unified-audit/materialize` | pass | `UnifiedAuditPanel.tsx` `runMaterialize` |
| 过滤参数透传 streams/package/action_prefix | pass | 同上 body |
| 写总线列表 → GET `/unified-audit/bus` | pass | `viewMode=bus` → `reload()` |
| UI 诚实锁 certified=false | pass | reload / materialize / gate |
| tsc | pass | frontend `tsc --noEmit` |

## 命令

```bash
cd aiPlat-management/frontend && npx tsc --noEmit
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| UI | `UnifiedAuditPanel.tsx` materialize / 写总线切换 |
| HTTP | J5 `POST …/materialize` · `GET …/bus` |

## 明确未做

- 任意 append 表单 / 全量运维台
- N24 / 附录 N 全量认证
