---
doc_type: Report
title: Phase 2 — Unified Audit UI 事件详情加深证据（N24 Batch J17）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / Unified Audit UI Event Detail（Batch J17）证据

> 实施权威：附录 N N24 partial 加深（事件行展开 refs/payload + 写总线 event_type 过滤）。  
> **未宣称** N24 certified / 全量运维台。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 事件行可展开详情 | pass | `UnifiedAuditPanel.tsx` expandedKey |
| 详情含 event_id / occurred_at / refs / payload | pass | 同上 |
| bus `event_type` 过滤 → GET `/unified-audit/bus` | pass | `reload()` extra.event_type |
| UI 诚实锁 certified=false | pass | reload 响应检查 |
| tsc | pass | frontend `tsc --noEmit` |

## 命令

```bash
cd aiPlat-management/frontend && npx tsc --noEmit
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| UI | `UnifiedAuditPanel.tsx` 事件详情 / event_type 过滤 |
| HTTP | J5 `GET …/bus?event_type=`；view/bus 列表已含 refs/payload |

## 明确未做

- JSON schema 编辑器 / 导出下载 / 全量运维台
- N24 / 附录 N 全量认证（审计面冻结见 `phase2-n24-unified-audit-freeze-evidence.md`）
