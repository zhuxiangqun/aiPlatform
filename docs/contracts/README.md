# FDE / FDA / Org L5 契约索引（阅读顺序与维护责任）

本目录存放 FDE 工作台演进与 **Org L5（组织级单线闭环）** 的跨仓契约与评审产物。Core 运行时契约仍在 `aiPlat-core/docs/contracts/`。

**总原则：先方案后改码。**  
- FDE Phase 0 已于 **2026-09-14** 宣布开工（见 [开工清单 v1](./FDE_PHASE0_KICKOFF_CHECKLIST.md) / [决策记录 v1](./FDE_DECISION_RECORD.md)）。  
- Org L5 **P0–P4 已接线**（含 Fleet 门禁与 [`ORG_L5_RUNBOOK.md`](./ORG_L5_RUNBOOK.md)；**未**开生产 live IO）。  
- **Phase C C0–C5 签收包就绪**，**C1.5 Interface YAML 已落地**（[`ORG_CHANNEL_INTERFACE_CHARTER.md`](./ORG_CHANNEL_INTERFACE_CHARTER.md)、[`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md)）；**未**做 M4 客户签收。  
- **K 波 K0–K5 已落地**，**F2 直写已拒绝**（令牌仅 `apply_proposal` / `rollback_proposal`；[`ORG_K_WAVE_CHARTER.md`](./ORG_K_WAVE_CHARTER.md)）。不称出错已变成规则；不替代 M4。
- **V 波 V0–V5 已落地**（[`ORG_V_WAVE_CHARTER.md`](./ORG_V_WAVE_CHARTER.md)）。不是 M4，也不是 L5。
- **E 波 E0–E2 已落地**（[`ORG_EDGE_ROLLBACK_CHARTER.md`](./ORG_EDGE_ROLLBACK_CHARTER.md)）。只撤回带快照的 merge 边。不是 M4。
- **H 波 H0–H5 已落地**（[`ORG_H_WAVE_CHARTER.md`](./ORG_H_WAVE_CHARTER.md)）。H4 沙箱开关开、live 拒。H5 人批才登记。不是 M4。

---

## 0. Org L5（组织级 / 企业大脑单线）— 推荐阅读顺序

| 顺序 | 文档 | 读什么 |
|:----:|------|--------|
| 1 | [`ORG_L5_CHARTER.md`](./ORG_L5_CHARTER.md) | L5 验收定义、非目标、阶段、话术 |
| 2 | [`ORG_L5_PILOT_SPEC.md`](./ORG_L5_PILOT_SPEC.md) | it-ops 试点故事、状态机、KPI、API 草图 |
| 3 | [`ORG_L5_DECISION_RECORD.md`](./ORG_L5_DECISION_RECORD.md) | D1–D5；**§5 D6–D10**；**§7 D-V**；**§8 D-E**；**§9 D-H** |
| 4 | [`ORG_L5_PHASE0_KICKOFF_CHECKLIST.md`](./ORG_L5_PHASE0_KICKOFF_CHECKLIST.md) | **勾完才准 Phase 1 改码** |
| 5 | [`ORG_CHANNEL_INTERFACE_CHARTER.md`](./ORG_CHANNEL_INTERFACE_CHARTER.md) | **Phase C**：渠道入站 / Interface / 岗位 / 用量 |
| 6 | [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md) | **C5 签收包**；≠ 客户已签字 |
| 7 | [`ORG_K_WAVE_CHARTER.md`](./ORG_K_WAVE_CHARTER.md) | **K 波 K0–K5**；不称规则已自动固化 |
| 8 | [`ORG_V_WAVE_CHARTER.md`](./ORG_V_WAVE_CHARTER.md) | **V 波 V0–V5**。不称 M4/L5 |
| 9 | [`ORG_EDGE_ROLLBACK_CHARTER.md`](./ORG_EDGE_ROLLBACK_CHARTER.md) | **E 波 E2**。带快照的 merge 边可撤回 |
| 10 | [`ORG_H_WAVE_CHARTER.md`](./ORG_H_WAVE_CHARTER.md) | **H 波 H0–H5**。H4 沙箱开、live 拒；H5 人批才登记 |

**注意**：本文 L5 ≠ 工厂 `release_engine` L5；≠ Action 阶梯 P2-L5 命名。

**操作手册入口（UI 真相）**：侧边栏以 `pageManifest` 为准——组织试点 `/org/pilot`、业务本体 `/knowledge/business`、知识库 `/knowledge/library`、应用工厂 `/app/factory`。合册索引见 [`../manuals/README.md`](../manuals/README.md)；FDE 导航见 [`../manuals/fde/README.md`](../manuals/fde/README.md)。

---

## 1. FDE 推荐阅读顺序（接手 / 评审）

| 顺序 | 文档 | 读什么 |
|:----:|------|--------|
| 1 | [`../architecture/plans/fde-workbench-evolution-plan.md`](../architecture/plans/fde-workbench-evolution-plan.md) | 方向、阶段、风险、非目标 |
| 2 | [`FDE_WORKBENCH_CONTRACT.md`](./FDE_WORKBENCH_CONTRACT.md) | 控制台边界、两类 Action、否定清单、**路径事实** |
| 3 | [`FDE_GUARD_REGISTRY_LANDING.md`](./FDE_GUARD_REGISTRY_LANDING.md) | 接到现有 guard/Registry/Store；**§2.0 路径修正** |
| 4 | [`audit_schema.v1.yaml`](../../aiPlat-core/core/harness/schemas/audit_schema.v1.yaml) | 审计字段、Eval 门、变更面白名单 |
| 5 | [`domain_literals_scan.md`](./domain_literals_scan.md) + [`action_branch_scan.md`](./action_branch_scan.md) | 存量量化与分类 |
| 6 | [`FDE_DECISION_RECORD.md`](./FDE_DECISION_RECORD.md) | 六问、假设、依赖、生效门禁 |
| 7 | [`FDE_PHASE0_KICKOFF_CHECKLIST.md`](./FDE_PHASE0_KICKOFF_CHECKLIST.md) | **勾完即开工** |
| 8 | [`FDE_WORKBENCH_GUARD_AND_AUDIT_MAPPING.md`](./FDE_WORKBENCH_GUARD_AND_AUDIT_MAPPING.md) | Phase 0/1 实施设计骨架（开工后） |
| 9 | [`audit_mapping_report.md`](./audit_mapping_report.md) | Phase 1 dry-run：schema↔ActionStore 分类报告 |
| 10 | [`FDE_PHASE1_HITL_SMOKE.md`](./FDE_PHASE1_HITL_SMOKE.md) | Phase 1 HITL 冒烟（自动化 + 手工） |

---

## 2. 依赖关系（简图）

```
演进方案 v1.1+
    ├── Workbench Contract ──┐
    ├── audit_schema.v1      ├──→ 决策记录（六问 + 六件套门禁）
    ├── Guard Landing        │         │
    ├── domain_literals_scan ┘         ▼
    └── action_branch_scan  ──→  Phase 0 开工清单 §E 签字
                                         │
                                         ▼
                              Guard/Audit Mapping（实施顺序）

Org L5（并行）
    Charter → Pilot Spec → Decision D1–D5 → Kickoff §E
         │
         ├──→ Phase 1…P4：connector fetch → OrgRun → Fleet/Runbook
         └──→ Phase C：Channel/Interface Charter（D6–D10）→ C1 Interface → C2 飞书入站
              M4 客户真线独立跟踪
```

---

## 3. 文件一览与维护责任

| 文件 | 状态 | 建议维护人 |
|------|------|------------|
| **`ORG_L5_CHARTER.md`** | **v1.5 · P0–P4** | 架构 |
| **`ORG_L5_PILOT_SPEC.md`** | **v1.0 · 规格冻结** | 架构 / 试点 Owner |
| **`ORG_L5_DECISION_RECORD.md`** | **v1.4 · D1–D10 + D-V + D-E + D-H** | **记录人**（每周） |
| **`ORG_L5_PHASE0_KICKOFF_CHECKLIST.md`** | **v1.0 · Phase 1 已宣布** | 检查人 / 复核人 |
| **`ORG_CHANNEL_INTERFACE_CHARTER.md`** | **v1.5 · C5 签收包就绪** | 架构 / Org Owner |
| **`ORG_M4_SIGNOFF_PACK.md`** | **v1.0 · 包就绪，未签字** | 试点 Owner |
| **`ORG_K_WAVE_CHARTER.md`** | **v1.6 · K5 落地；F2 直写已拒绝** | 架构 / Org Owner |
| **`ORG_V_WAVE_CHARTER.md`** | **v1.0 · V0–V5 已落地；不称 M4** | 架构 / Org Owner |
| **`ORG_EDGE_ROLLBACK_CHARTER.md`** | **v1.0 · E2 已落地；不称 M4** | 架构 / Org Owner |
| **`ORG_H_WAVE_CHARTER.md`** | **v1.0 · H0–H5 已落地；H4 沙箱开、live 拒；H5 人批才登记** | 架构 / Org Owner |
| **`ORG_L5_RUNBOOK.md`** | **现场运行** | 试点 Owner |
| 演进方案 | v1.1+ 待评 | 架构 |
| `FDE_WORKBENCH_CONTRACT.md` | 待评 | 架构 |
| `FDE_GUARD_REGISTRY_LANDING.md` | v1.1 待评 | 架构 / 平台 |
| `audit_schema.v1.yaml` | 语义冻结待评 | 平台 / harness |
| `domain_literals_scan.md` | 初扫；分类待签字 | 记录人 + 复核 |
| `action_branch_scan.md` | v0.2；P8 待签字 | 记录人 + 复核 |
| `FDE_DECISION_RECORD.md` | v0.3 填写中 | **记录人**（§6 每周） |
| `FDE_PHASE0_KICKOFF_CHECKLIST.md` | v0.1 | 检查人 / 复核人 |
| `FDE_WORKBENCH_GUARD_AND_AUDIT_MAPPING.md` | v0.2 设计 | 平台（开工后） |

---

## 4. 评审周三件事（纪律）

### FDE

1. **路径修正**（清单 §B）— 不做则守卫扫空  
2. **六问 Owner + Deadline**（决策记录）— 不做则决策悬空  
3. **六件套 + 开工清单 §E** — 缺一不可，否则不开工  

### Org L5

1. **五问 D1–D5 书面确认** — 不做则 Pilot 漂移  
2. **Kickoff §E** — 缺一不可，否则不准 Phase 1 改码  
3. **话术**：未达 M4 不称全域企业大脑 / OpenAI L5 已达成  

---

## 5. 路径速查

| 层 | 路径 |
|----|------|
| 前端工作台 | `aiPlat-management/frontend/src/pages/Diagnostics/` |
| 后端 FDE | `aiPlat-platform/apps/fde/` |
| API | `/api/platform/apps/fde` |
| Org（规划） | `aiPlat-platform/apps/org/`（D4 确认后） |
| 守卫引擎 | `scripts/architecture_guard.py` + `arch_guard_rules*` |

**MUST**：FDE 工作台改动的 PR 勾选 `FDE_WORKBENCH_CONTRACT.md` §4/§7。  
**MUST**：Org L5 改码 PR 勾选 `ORG_L5_CHARTER.md` §3 否定清单 + Kickoff 已宣布 Phase。
