---
doc_type: Report
title: Phase 2 — Unified Audit UI 流过滤加深证据（N24 Batch J12）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / Unified Audit UI Streams（Batch J12）证据

> 实施权威：附录 N N24 partial 加深（管理端统一审计面板暴露 `action_store` / `fact_query_audit` 流过滤）。  
> **未宣称** 写总线 / N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| STREAM_OPTIONS 含 action_store | pass | `UnifiedAuditPanel.tsx` |
| STREAM_OPTIONS 含 fact_query_audit | pass | 同上 |
| 过滤参数仍走 `streams=` | pass | `reload()` → `/unified-audit?streams=` |
| UI 诚实锁 certified=false | pass | `reload()` / `runGate()` |
| tsc / build | pass | frontend `tsc --noEmit` + `npm run build` |

## 命令

```bash
cd aiPlat-management/frontend && npx tsc --noEmit && npm run build
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| UI | `UnifiedAuditPanel.tsx` `STREAM_OPTIONS` |
| HTTP | J3 `/unified-audit?streams=action_store|fact_query_audit` |
| 后端流 | J7 ActionStore + J10 FactQuery view |

## 明确未做

- N24 / 附录 N 全量认证

> materialize / 写总线列表见 Batch J13：`phase2-unified-audit-ui-materialize-evidence.md`。
