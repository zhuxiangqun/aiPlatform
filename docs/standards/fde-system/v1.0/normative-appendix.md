---
doc_type: Standard
status: active
authority: canonical
doc_id: FDE_SYS_V10_APPENDIX
purpose: FDE 系统 v1.0 规范性附录
scope_in: 附录 A–H、N；签收与部署约束
scope_out: 实现状态声明、扩大 ADR-09 范围
owner: 朱向群
version: 1.0.0
last_reviewed: 2026-11-26
review_cycle: 90d
---
# aiPlat FDE 系统规范性附录 v1.0

> 配套白皮书；与正文同等效力（2026-12-01 起）。用语 MUST / MUST NOT / SHOULD / MAY。  
> 与已批准 ADR-09 冲突时，部署边界以 ADR 为准。  
> 机读：`schemas/fde-system.v1.0.schema.json` + `conformance-checklist.yaml`。

## 附录地图

| 小节 | 内容 |
|---|---|
| 0 | 约定 |
| A | 架构归属 |
| B | 签收入口 |
| C | 证据绑定 |
| D | 工件 / 会话 |
| E | UX |
| F | 部署 |
| G | 与评测/外援/知识 |
| H | 安全 |
| N | Conformance Checklist |

---

## 0. 约定

同评测附录 0。

---

## A. 架构归属

| 层 | MUST |
|---|---|
| HTTP | `aiPlat-platform/apps/fde/api/` + 前缀 `/api/platform/apps/fde` |
| 业务无 HTTP | `aiPlat-core/core/apps/fde/` 经 CoreFacade |
| 禁止 | platform → harness 直连；第二套验收系统 |

---

## B. 签收入口

| 规则 | 等级 |
|---|---|
| Canonical `POST …/acceptance/signoff` | MUST |
| 平行签收路径 | MUST NOT |
| 前端消费上述前缀 | MUST |

### 错误码（最小集）

| code | 含义 |
|---|---|
| `fde.signoff_entry_not_canonical` | 非唯一签收入口 |
| `fde.evidence_required` | 策略要求证据缺失 |
| `fde.tenant_mismatch` | 租户不匹配 |
| `fde.parallel_acceptance_forbidden` | 平行验收系统 |

---

## C. 证据绑定

- 签收记录 MUST 含 `actor`、`tenant_id`、`timestamp`；
- 切片策略开启时 MUST 校验诊断 `report_id`（或等价证据引用）；
- 无证据对外「已交付验收」→ MUST NOT。

---

## D. 工件 / 会话

- 可选独立 home 子目录；
- 工件权威在 FDE 存储/API，MUST NOT 以 Wiki 为签收源。

---

## E. UX

- 工作台 MUST NOT 提供平行签收 API；
- 链出诊断/评测页时 SHOULD 标明非签收面。

---

## F. 部署

| 模式 | 规则 |
|---|---|
| 共部署 | 合法默认；回滚目标 |
| 可选独立进程 | MAY；同路由语义；非默认强制 |
| compose 长驻 | MUST 另批；本附录不授权 |
| one-shot health | MAY |

回滚顺序 MUST 可执行：停独立 → 共部署 → 既有 signoff。

---

## G. 与评测 / 外援 / 知识

- 评测 GateResult MUST NOT 自动写成 FDE 签收；
- ImportReport MUST NOT 代替签收；
- 知识手册同步 MUST NOT 改变签收权威源。

---

## H. 安全

- 身份透传 MUST；跨租户签收 MUST 拒；
- 权限不在 FDE 内重复实现绕过 PolicyGate 的平行检查链（遵循平台「审批单次检查」纪律）。

---

## N. Conformance Checklist

| ID | 等级 | 项 | Core |
|---|---|---|---|
| F01 | Core | 唯一 signoff 入口 | MUST |
| F02 | Core | 无平行验收 API | MUST |
| F03 | Core | CoreFacade 访问 core；无 harness 直连 | MUST |
| F04 | Core | 签收记录含 actor/tenant/时间 | MUST |
| F05 | Core | 路由前缀 `/api/platform/apps/fde` | MUST |
| F06 | Core | 回滚到共部署路径可文档化 | MUST |
| F07 | Extended | 切片 report_id 绑定策略 | SHOULD |
| F08 | Extended | 工作台完整签收面 | SHOULD |
| F09 | Extended | 可选独立进程文书 + health | SHOULD |
| F10 | Operational | 生产独立进程 authorize | MAY |
| F11 | Operational | compose 长驻（另批 ADR） | MAY |

`core_ready` = F01–F06；`certified` 须非作者批准 + 证据。

### N.1 代码证据快照（2026-11-26 · 测量，非认证）

权威测量报告：`reports/products/fde-system/v1.0/core-gap-evidence.md`。

| ID | 测量状态 | 一句话 |
|---|---|---|
| F01 | exists | 唯一 `POST …/acceptance/signoff` |
| F02 | exists | 无平行 FDE 验收写入口（org GET /signoff 另轨） |
| F03 | exists | 无 harness / `core.apps.skills` 直导；经 CoreFacade |
| F04 | exists | record 含 tenant_id / actor / signed_at（缺省可回落 default） |
| F05 | exists | `/api/platform/apps/fde` 注册与前端一致 |
| F06 | exists | README + ADR-09 回滚文书 |
| F07 | exists | `validate_slice_signoff_reports` + 切片签收禁 default tenant |
| F08 | exists | AcceptTab → 唯一 `acceptance/signoff` |
| F09 | exists | `adr09_fde_optional_health_*` 脚本 + `fde_optional_process_contract` |
| F10 | exists | `evaluate_fde_production_process_authorize`；**authorized=false** |
| F11 | exists | `evaluate_fde_compose_long_running_authorize`；须 `adr_ref`；**authorized=false** |

**测量：Core/Extended/Operational 项均为 exists；F10–F11 authorized=false；compose 长驻=否。**  
正式徽章待非作者复核。`certified`：否。ADR-09 边界未扩大。  
证据：`core|extended|operational-gap-evidence.md`。
