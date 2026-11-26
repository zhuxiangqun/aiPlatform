---
doc_type: Report
doc_id: FDE_SYS_V10_CORE_GAP
status: measurement
authority: evidence
created: 2026-11-26
last_reviewed: 2026-11-26
purpose: FDE 系统 v1.0 附录 N Core（F01–F06）代码证据盘点；非 certified
---

# FDE 系统 v1.0 — Core 差距证据（测量）

> **性质**：测量报告。部署边界仍以已批准 `ADR09_FDE_BOUNDARY.md` 为准。  
> **刷新**：2026-11-26 收口 F03/F04 代码后重测。

## 总判定

| 问题 | 结论 |
|---|---|
| 能否宣称 `core_ready`？ | **是（conditional）**：F01–F06 exists + 非作者 Security 朱鸿林复核（`core-approval-record.approved.json`）；ADR-09 边界未扩大 |
| 能否宣称 `certified`？ | **否** |

## F01–F06

| ID | 状态 | 证据 | 缺口 |
|---|---|---|---|
| F01 唯一 signoff | **exists** | `apps/fde/api/fde_acceptance.py` `POST /acceptance/signoff`；委托 `validate_slice_signoff_reports`；`slice_evidence.py:384` | — |
| F02 无平行验收 API | **exists** | 全仓 FDE 写签收仅此路径；optional health 不暴露 signoff | org `GET /signoff*` 另轨（监视） |
| F03 CoreFacade / 无 harness 直连 | **exists** | `apps/fde` 下 `from core.harness` → 0；`from core.apps.skills` → 0；verify/extras/install 经 `core.api.core_facade`（`verify_skill_acceptance` / `get_skill_registry`） | — |
| F04 签收含 actor/tenant/时间 | **exists** | record 含 `tenant_id`、`tenant_resolved_from`、`signed_by`/`actor_id`、`signed_at`（`fde_acceptance.py` `_tenant_for_signoff` + signoff handler） | 无显式 tenant 时回落 `DomainRouter.default_tenant()`（`tenant_resolved_from=default`）；非空强制可作 Extended |
| F05 前缀 `/api/platform/apps/fde` | **exists** | `registry/apps.yaml:23`；前端 `/api/platform/apps/fde` | — |
| F06 回滚共部署可文档化 | **exists** | `apps/fde/README.md`；`ADR09_FDE_BOUNDARY.md` 回滚总则 | — |

## 复现命令

```bash
rg -n 'acceptance/signoff|tenant_id|_tenant_for_signoff' aiPlat-platform/apps/fde/api/fde_acceptance.py
rg -n 'from core\.harness|from core\.apps\.skills' aiPlat-platform/apps/fde --glob '*.py'   # 预期空
rg -n 'verify_skill_acceptance|get_skill_registry' aiPlat-platform/apps/fde/api/fde.py
```
