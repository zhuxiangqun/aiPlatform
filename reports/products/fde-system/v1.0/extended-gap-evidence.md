---
doc_type: Report
doc_id: FDE_SYS_V10_EXT_GAP
status: measurement
authority: evidence
created: 2026-11-26
last_reviewed: 2026-11-26
purpose: FDE 系统 v1.0 附录 N Extended（F07–F09）代码证据盘点；非 certified
---

# FDE 系统 v1.0 — Extended 差距证据（测量）

> **性质**：测量报告。不扩大 ADR-09；compose 长驻仍未授权。  
> **刷新**：2026-11-26 Extended F07–F09 收口后。

## 总判定

| 问题 | 结论 |
|---|---|
| F07–F09 测量 | **exists** |
| 正式 extended_ready | **是（conditional）**：朱莹非作者复核（`extended-approval-record.approved.json`） |
| certified | **否** |
| compose 长驻（F11） | **否**（`ADR-FDE-COMPOSE-LONG-RUNNING` Proposed ≠ Accepted） |
| F10 生产独立 authorize | **是**（operational-approval-record；朱莹） |

## F07–F09

| ID | 状态 | 证据 | 缺口 |
|---|---|---|---|
| F07 切片 report_id 绑定 | **exists** | `validate_slice_signoff_reports`；`fde_slice_report_binding_policy`；signoff HTTP 409 阻断；切片签收禁 `tenant_resolved_from=default` | — |
| F08 工作台完整签收面 | **exists** | `FdeDashboard` AcceptTab → checklist + signoff；`fde_workbench_signoff_surface`；无平行签收 API | — |
| F09 可选独立进程 + health | **exists** | `scripts/adr09_fde_optional_health_server.py` + `adr09_fde_optional_phase_health.sh`；`fde_optional_process_contract`（`compose_long_running_authorized=false`） | 生产 authorize = F10 |

## 复现命令

```bash
pytest aiPlat-core/core/tests/unit/test_apps/test_fde_extended_f07_f09.py -q
rg -n 'validate_slice_signoff_reports|explicit_tenant_required|AcceptTab' \
  aiPlat-core/core/apps/fde aiPlat-platform/apps/fde \
  aiPlat-management/frontend/src/pages/Diagnostics/FdeDashboard.tsx | head -30
```
