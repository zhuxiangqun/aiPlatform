---
doc_type: Report
title: Phase 2 — Unified Audit 管理端 UI 证据（N24 Batch J4）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Unified Audit UI（Batch J4）证据

> 实施权威：附录 N N24 partial 加深（知识工厂统一审计只读薄面板；经 J3 HTTP→CoreFacade）。  
> **未宣称** 写总线表 / N24 certified。
>
> 流过滤加深见 Batch J12：`phase2-unified-audit-ui-streams-evidence.md`。  
> materialize / 写总线列表见 Batch J13：`phase2-unified-audit-ui-materialize-evidence.md`。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 面板挂载于知识工厂「更多」区 | pass | `KnowledgeFactoryPage.tsx` → `<UnifiedAuditPanel />` |
| 列表/过滤走 `/api/platform/apps/fde/unified-audit` | pass | `UnifiedAuditPanel.tsx` |
| UI 拒绝 certified=true 汇合回执 | pass | `reload()` 诚实锁 |
| suite/gate 按钮暴露诚实锁 | pass | `runGate()` |
| tsc / build | pass | frontend `tsc --noEmit` + `npm run build` |

## 命令

```bash
cd aiPlat-management/frontend && npx tsc --noEmit && npm run build
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| UI | `aiPlat-management/frontend/src/pages/KnowledgeFactory/UnifiedAuditPanel.tsx` |
| 宿主 | `KnowledgeFactoryPage` 「更多」折叠区 |
| HTTP | J3 `…/fde/unified-audit*` → CoreFacade |

## 明确未做

- 强制全量事件进 ActionExecution / Package·Action 热路径全量写 bus
- N24 / 附录 N 全量认证

> 写总线见 Batch J5：`phase2-unified-audit-bus-evidence.md`。
