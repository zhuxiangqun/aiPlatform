# FDE / FDA 契约索引（阅读顺序与维护责任）

本目录存放 FDE 工作台演进的**跨仓契约与评审产物**。Core 运行时契约仍在 `aiPlat-core/docs/contracts/`。

**总原则：先方案后改码。** Phase 0 已于 **2026-09-14** 宣布开工（见 [开工清单 v1](./FDE_PHASE0_KICKOFF_CHECKLIST.md) / [决策记录 v1](./FDE_DECISION_RECORD.md)）。

---

## 1. 推荐阅读顺序（接手 / 评审）

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
```

---

## 3. 文件一览与维护责任

| 文件 | 状态 | 建议维护人 |
|------|------|------------|
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

1. **路径修正**（清单 §B）— 不做则守卫扫空  
2. **六问 Owner + Deadline**（决策记录）— 不做则决策悬空  
3. **六件套 + 开工清单 §E** — 缺一不可，否则不开工  

---

## 5. 路径速查

| 层 | 路径 |
|----|------|
| 前端工作台 | `aiPlat-management/frontend/src/pages/Diagnostics/` |
| 后端 FDE | `aiPlat-platform/apps/fde/` |
| API | `/api/platform/apps/fde` |
| 守卫引擎 | `scripts/architecture_guard.py` + `arch_guard_rules*` |

**MUST**：FDE 工作台改动的 PR 勾选 `FDE_WORKBENCH_CONTRACT.md` §4/§7。
