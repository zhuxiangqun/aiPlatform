---
doc_type: Standard
status: active
authority: canonical
doc_id: FDE_SYS_V10_WHITEPAPER
purpose: 定义 aiPlat FDE（交付验收）系统 v1.0 目标架构与强制要求
scope_in: 交付闭环、签收唯一入口、证据绑定、工作台边界、可选独立进程、符合性（附录 N）
scope_out: 评测 accuracy、外援 L2 自动授予、compose 长驻默认、新建第二套验收系统
owner: 朱向群
version: 1.0.0
last_reviewed: 2026-11-26
review_cycle: 90d
---
# aiPlat FDE 系统技术白皮书 v1.0

> **版本**：v1.0.0 · 2026-11-26  
> **状态**：已批准；**2026-12-01 生效**  
> **性质**：技术标准（`authority: canonical`）  
> **构成**：正文 + 规范性附录 + `schemas/`  
> **批准**：`ADR-FDE-SYS-v1.0-2026-11-26.md`  
> **诚实边界**：标准批准 ≠ 实现 certified；compose 长驻仍须另批 ADR-09。

---

## 标准声明

效力 / 构成 / 冲突裁决同评测系统白皮书模式（草案 → 批准 → 符合性单独认证）。  
与 ADR-09 边界冲突时：部署边界以已批准 ADR 为准，本标准草案不得扩大范围。

---

## 文档地图

| 正文 | 内容 | 附录 |
|---|---|---|
| 0–2 | 概览、痛点、原则 | — |
| 3 | 架构与归属 | A |
| 4 | 签收唯一入口 | B |
| 5 | 证据 / 诊断绑定 | C |
| 6 | 交付工件与会话 | D |
| 7 | 工作台 UX | E |
| 8 | 部署（共部署 / 可选独立） | F |
| 9 | 与评测 / 外援 / 知识 | G |
| 10 | 安全与多租户 | H |
| 11 | 路线图 | — |
| 12 | 迁移与回滚 | — |
| 13 | 符合性认证 | N |
| 14 | 实施参考 | — |
| 15 | 结论 | — |

---

## 0. 先看一页

FDE 要解决的不是「再做一个诊断页」，而是：

> **客户交付闭环：证据可引用、签收唯一、可回滚、不与评测/外援入口混淆。**

失败模式：

- **平行签收 API**；
- **用评测绿代替客户签收**；
- **未另批就 compose 长驻 / 强制独立进程**；
- **platform 直连 harness 绕过 CoreFacade**。

目标链路：

> **诊断/切片证据 → 交付工件 → 唯一 signoff → 审计 →（可选）独立进程。**

---

## 1. 痛点（摘要）

1. 签收与诊断入口分散；  
2. 无 `report_id` 仍宣称可交付；  
3. 工作台与「第二套验收系统」冲动；  
4. 把 FDE 拆仓当成 v1 前置；  
5. 与评测中心职责混用。

---

## 2. 原则

| # | 原则 |
|---|---|
| 1 | **签收唯一**：`POST …/fde/acceptance/signoff` 为权威；禁止平行入口 |
| 2 | **评测 ≠ 签收**：工程门禁与客户验收分轨 |
| 3 | **独立可选**：共部署是合法生产态；独立进程须显式授权，长驻另批 |

---

## 3. 架构与归属

```text
Experience     FDE 工作台（management）
API            /api/platform/apps/fde（唯一前缀语义）
Service        core/apps/fde（经 CoreFacade）
Evidence       slice / diagnosis report 绑定
Deploy         共部署默认；可选独立进程（同路由语义）
```

- HTTP 在 `aiPlat-platform/apps/fde/api/`；
- 无 HTTP 业务在 `aiPlat-core/core/apps/fde/`；
- platform MUST NOT 直连 harness。

---

## 4. 签收唯一入口

- Canonical：`POST /api/platform/apps/fde/acceptance/signoff`；
- 实现委托 `validate_slice_signoff_reports`（或后继同语义函数）；
- MUST NOT 新增第二套 `/acceptance/signoff` 或等价平行路径；
- 前端 MUST 消费上述前缀。

---

## 5. 证据 / 诊断绑定

- 切片场景 SHOULD/按策略 MUST 绑定诊断 `report_id`（D2 开关既有）；
- 签收记录 MUST 可追溯 actor / tenant / 证据引用；
- 无证据时 MUST NOT 对外宣称「已验收交付」。

---

## 6. 交付工件与会话

- 交付会话 / 工件可落独立 home 子目录（可选）；
- 与控制面库隔离为 SHOULD，不是 Core 阻断项；
- 工件权威不落到 Wiki 页面（知识体系边界）。

---

## 7. 工作台 UX

- Canonical 工作台消费 `/api/platform/apps/fde`；
- 诊断工具可链入，但 MUST 标明「非签收面」若仅展示；
- 禁止把评测中心 `/eval` 做成签收入口。

---

## 8. 部署

| 模式 | 标准态度 |
|---|---|
| 控制面共部署 | 合法默认 / 回滚目标 |
| 正式可选独立进程 | 允许；同路由语义；非强制默认 |
| compose 长驻 | MUST 另批 ADR；本标准不授权 |
| one-shot health | 允许试点 |

回滚：停独立进程 → 共部署路径 → 签收仍走既有 signoff。

---

## 9. 与其他系统

| 系统 | 关系 |
|---|---|
| 评测 | 评测挡回归；FDE 挡客户签收；结果字段不得互换 |
| 外援 | 客户外援交付须 FDE 签收；ImportReport ≠ 签收 |
| 知识 | 手册可同步 Wiki；签收权威在 FDE API |
| 诊断 / Pi | 消费者关系：引用 report；不扩大其范围 |

---

## 10. 安全与多租户

- 签收 MUST 注入 tenant/actor；
- 跨租户签收 MUST 拒绝；
- 权限判断走平台既有 Policy / 身份透传规范。

---

## 11–12. 路线图与迁移

```text
Draft → Core（唯一 signoff + 证据绑定 + CoreFacade）
     → Extended（工作台完整面 / 可选独立进程文书）
     → Operational（生产独立进程 authorize / 长驻另批）
```

迁移：禁止新建平行验收系统；旧实验入口 → redirect 或删除时间表写入 ADR。

---

## 13. 符合性认证

附录 N；`exists` ≠ `certified`。  
部署边界仍受 ADR-09 约束。

---

## 14. 实施参考

`docs/architecture/plans/fde-system-v1.0-implementation-plan.md`。

---

## 15. 结论

FDE 标准把交付验收写成唯一签收、证据可绑、部署可回滚的契约；不与评测/外援抢入口，不把可选独立进程写成强制。
