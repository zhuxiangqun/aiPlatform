---
doc_type: Report
title: Phase 2 — Revision Restore HTTP 薄路由证据（N24 Batch J1）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Revision Restore HTTP（Batch J1）证据

> 实施权威：附录 N N24 partial 加深（平台 HTTP 暴露审批式 restore / audit / bridge；经 CoreFacade）。  
> **未宣称** 管理端回滚/审批 UI / Package+Action 全量总线合并 / N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| GET requests 经 Facade | pass | `test_list_requests_delegates_to_facade` |
| POST request/approve/reject + bridges | pass | `test_request_approve_reject_and_bridges` |
| ValueError → HTTP 400 | pass | `test_ledger_error_maps_to_400` |
| GET audit + POST suite | pass | `test_audit_and_suite_delegate` |
| gate certified 恒 false | pass | `test_gate_honesty_certified_false` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-platform/tests/test_revision_restore_http_phase2.py -v
# 预期：5 passed
```

实测（2026-11-17）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 路由 | `apps/fde/api/revision_restore_routes.py`（挂 `router.py` `/fde`） |
| HTTP | `GET/POST …/fde/revision-restore/requests*` · `…/approve` · `…/reject` · `GET …/audit` · `GET …/action-bridges` · `POST …/suite` · `POST …/gate` |
| Facade | `fact_ledger_*_revision_restore*` / `fact_ledger_list_revision_audit` / `fact_ledger_list_revision_action_bridges` / suite/gate |

## 明确未做

- 管理端回滚/审批 UI
- Package+Action 全量统一审计总线合并
- 强制所有直连 `restore_*` 必须走 HTTP 审批
- N24 / 附录 N 全量认证
