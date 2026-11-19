---
doc_type: Report
title: Phase 2 — Revision Restore 管理端 UI 证据（N24 Batch J2）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Revision Restore UI（Batch J2）证据

> 实施权威：附录 N N24 partial 加深（知识工厂审批式 restore 薄面板；经 J1 HTTP→CoreFacade）。  
> **未宣称** Package+Action 全量统一审计总线合并 / N24 certified / 一键全域回滚。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 面板挂载于知识工厂「更多」区 | pass | `KnowledgeFactoryPage.tsx` → `<RevisionRestorePanel />` |
| 请求/批准/拒绝/audit 走 `/api/platform/apps/fde/revision-restore/*` | pass | `RevisionRestorePanel.tsx` |
| UI 侧禁止 requester===approver 自批 | pass | `decide()` 前置校验 |
| suite/gate 按钮暴露诚实锁（certified 须 false） | pass | `runGate()` |
| tsc | pass | `npx tsc --noEmit`（frontend） |

## 命令

```bash
cd aiPlat-management/frontend && npx tsc --noEmit
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| UI | `aiPlat-management/frontend/src/pages/KnowledgeFactory/RevisionRestorePanel.tsx` |
| 宿主 | `KnowledgeFactoryPage` 「更多」折叠区 |
| HTTP | J1 `…/fde/revision-restore/*` → CoreFacade |

## 明确未做

- Package+Action 全量统一审计总线合并
- 强制所有直连 `restore_*` 必须经本 UI
- N24 / 附录 N 全量认证
