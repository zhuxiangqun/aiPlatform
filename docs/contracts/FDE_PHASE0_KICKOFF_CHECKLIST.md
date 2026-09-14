# FDE Phase 0 开工检查清单

| 字段 | 值 |
|------|-----|
| 文档 ID | `FDE-CHK-PHASE0-2026-09` |
| 版本 | **v1**（已签字开工） |
| 关联 | [`FDE_DECISION_RECORD.md`](./FDE_DECISION_RECORD.md) v1 · 方案 v1.1+ |
| 检查人 | Oliver Zhu |
| 复核人 | Oliver Zhu |
| 开工宣布日 | **2026-09-14** |

> 全部 A/B/C/D/E 已勾选。Phase 0 **已宣布开工**。

---

## A. 文档齐套

- [x] 方案 v1.1+ / v1.1++
- [x] `FDE_WORKBENCH_CONTRACT.md`（含 §4 路径事实）
- [x] `audit_schema.v1.yaml`
- [x] `FDE_GUARD_REGISTRY_LANDING.md` v1.1（§2.0 路径修正）
- [x] `domain_literals_scan.md`（分类框架已确认）
- [x] `action_branch_scan.md`（硬违规≈0；P8 表已建，抽查人签字见下）
- [x] `FDE_DECISION_RECORD.md` v1（六问已决；D5 延期）
- [x] `FDE_WORKBENCH_GUARD_AND_AUDIT_MAPPING.md` v0.2

签名：Oliver Zhu / 2026-09-14

---

## B. 路径修正

- [x] 待建规则须用 `aiPlat-management/frontend/src/pages/Diagnostics/**/*.{ts,tsx}`
- [x] `FdeWorkbenchForbiddenFrontendCheck` 已扫 Diagnostics
- [x] `fde_no_workbench_direct_harness` → `aiPlat-platform/apps/fde`
- [x] Contract §4 / Landing §2.0 已写路径事实
- [x] 契约内错误 scope 仅作「禁止示例」出现，非真相源

签名：Oliver Zhu / 2026-09-14

---

## C. 决策与假设

### C1. 六问已决

| ID | 决议 | Owner | Deadline | 已决？ |
|----|------|-------|----------|--------|
| D1 | 归档/删除 Orchestrator | Oliver Zhu | 2026-09-14 | ☑ |
| D2 | 允许跟踪域常量；禁行为分叉 | Oliver Zhu | 2026-09-14 | ☑ |
| D3 | Phase 2 新 id+别名；Phase 3 废弃 | Oliver Zhu | 2026-10-15 | ☑ |
| D4 | 硬门 200；P95=execute→audit | Oliver Zhu | 2026-10-15 | ☑ |
| D5 | 采纳建议；延期 Phase 4 | Oliver Zhu | Phase 4 立项 | ☑ 延期 |
| D6 | 禁止通过率唯一 KPI | Oliver Zhu | 2026-09-14 | ☑ |

### C2. 假设确认

- [x] A1–A8 已在决策记录勾选接受（A4/A6 待阶段验证）

**未确认假设**：无

### C3. D5 延期责任人

- [x] 已指定：**Oliver Zhu**

签名：Oliver Zhu / 2026-09-14

---

## D. Phase 0 最小项清单

| # | 项 | 动作 | 回滚 | Owner |
|---|-----|------|------|-------|
| 1 | API 前缀统一 | 前端/文档只推 `/api/platform/apps/fde`；旧路径标兼容 | 恢复兼容标注 | Oliver Zhu |
| 2 | Tab⑤ 文案 | 「平台离线包」；灰态「启动交付」 | 文案回退 | Oliver Zhu |
| 3 | Orchestrator | 按 D1 归档/删除 | 恢复文件 | Oliver Zhu |
| 4 | dashboard stub | 真数据或隐藏 | 恢复隐藏 | Oliver Zhu |
| 5 | 契约引用入库 | 已齐 | 文档回退 | Oliver Zhu |
| 6 | 守卫规则合入 | 假进度/拓扑 **warning**（Diagnostics 路径） | 删规则 | Oliver Zhu |
| 7 | 扫描报告回填 | domain 分类细化；action P8 签字 | 文档回退 | Oliver Zhu |

**Phase 0 不做**：lock-service 大规模种子 · Evolve · 多客户 · 审计表破坏性迁移。

签名：Oliver Zhu / 2026-09-14

---

## E. 开工签字

| 角色 | 姓名 | 日期 |
|------|------|------|
| 架构 | Oliver Zhu | 2026-09-14 |
| 产品 / FDE 负责人 | Oliver Zhu | 2026-09-14 |
| 记录人 | Oliver Zhu | 2026-09-14 |

**Phase 0 开工宣布：** ☑ **是**（生效日 **2026-09-14**）

---

## F. 开工后首周检查点

- [ ] 守卫 warning 观察，记录误报
- [ ] 决策记录 §6 首次周更
- [x] 最小项 1–5 完成或明确逾期（2026-09-14 已完成 1–6）
- [x] D1 归档路径 + CAPABILITIES 更新（`service/_archive/builder.py`）

---

## G. 快速回滚总览

| 变更 | 回滚方式 |
|------|----------|
| 前端规则合入 | 删除规则 |
| API 前缀统一 | 恢复兼容标注 |
| Tab⑤ 文案 | git revert |
| Orchestrator 归档 | 恢复文件 |
| 契约入库 | 文档回退版本号 |

**紧急熔断**：架构签字人可直接回滚，不等评审。

---

## 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1 | 2026-09-14 | 空清单 |
| **v1** | **2026-09-14** | 全勾选；宣布 Phase 0 开工 |
