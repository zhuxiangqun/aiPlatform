# C3 复核表 — contracts / plans 降噪（2026-10-23）

> 批次批准：用户「继续」下一批（C3）。**未批准 C4 删除。**

## 原则应用

| 类型 | 本批策略 |
|------|----------|
| 约束正文 / Charter / Runbook / 签收包 | **保留** `docs/contracts/` |
| 扫描/烟测过程纸（仍被脚本或契约引用） | **路径保留** + README §3.1 **阅读降权** |
| plans living（pi-thin / app-module-layout / DR / FDE 演进 / 五产品目标稿等） | **保留** |
| plans 无入链过程稿 / 已完成迁移方法论 / 被现行 comparison 取代的综合对比 | **迁 archive** |

## 迁 archive（7）

| 原路径 | 归档路径 | R1/R2 要点 |
|--------|----------|------------|
| `architecture/plans/comprehensive-comparison.md` | `archive/plans-comprehensive-comparison-2026-07.md` | 2026-07 综合对比；现行 SoT=`architecture/comparison.md` |
| `architecture/plans/deployment_checklist.md` | `archive/plans-deployment-checklist.md` | 0 入链；过程清单 |
| `architecture/plans/sft_rl_pipeline.md` | `archive/plans-sft-rl-pipeline.md` | 0 入链 |
| `architecture/plans/design-runtime-extension-slot.md` | `archive/plans-design-runtime-extension-slot.md` | 0 入链设计稿 |
| `architecture/plans/design-distribution-yaml.md` | `archive/plans-design-distribution-yaml.md` | 0 入链设计稿 |
| `architecture/plans/design-kanban-cron.md` | `archive/plans-design-kanban-cron.md` | 0 入链设计稿 |
| `architecture/plans/router-migration-plan.md` | `archive/plans-router-migration-plan.md` | 迁移已完成；仅历史方法论 |

**未迁**：五产品三件套（仍为非现状规划入口）、`pi-thin-runtime`、`app-module-layout`、`optimization-roadmap`（`meta_agent.py` 设计依据）、`worker-split-plan`（现行「不拆分」决策）、`fde-workbench-evolution-plan`、DR/observability/role/journey 等。

## contracts 降权（不迁路径）

`docs/contracts/README.md` 新增 **§3.1 过程留存**：`domain_literals_scan` / `action_branch_scan` / `audit_mapping_report` / `FDE_PHASE1_HITL_SMOKE` — 仍被契约/脚本引用，故 **R6=保留维护区 + 索引降权**。

## R3 处置摘要

| 引用 | 处置 |
|------|------|
| whitepaper suite YAML → comprehensive-comparison | 已改 archive 路径；已重生分卷 |
| `architecture-evolution-roadmap` → router-migration | 已改 archive 路径 |
| contracts README 扫描表 | 已移入 §3.1 |
| 外部留存 | **未核实·待确认** |

## 验收

| 项 | 结果 |
|----|------|
| 删除 | **0** |
| 迁 archive | **7** plans |
| 迁入文相对链接 | **broken 0** |
| 白皮书 volumes `--check` | **PASS** |
| C0 口径复测 | total **262** · maint **190**（相对 C2 末：−7 迁档 +1 本复核表） |
| C4 | **未实施** |
