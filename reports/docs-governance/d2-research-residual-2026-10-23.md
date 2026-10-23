# D2 复核 — research 规划/审计残留（2026-10-23）

> 批准：用户「继续」（D1 之后下一批）。方案：`docs/research/docs-reasonable-reduction-plan-2026-10.md` §3.2。

## 裁定摘要

| 文件 | Q1 现行责任 | Q2 留存 | R6 |
|------|-------------|--------|-----|
| `plan-app-factory-l2-expected-behavior-manual.md` | **有**：`06-acceptance-contract` MUST `ls`/`grep` 本路径 | — | **保留** `docs/research/` |
| `plan-app-factory-l2-import-repo.md` | 同上 | — | **保留** |
| `plan-app-factory-l3-incremental-engine.md` | 同上 | — | **保留** |
| `plan-app-factory-l4-multi-module.md` | 同上 | — | **保留** |
| `plan-app-factory-l45-db-migration.md` | 同上 | — | **保留** |
| `plan-app-factory-l5-cicd.md` | 同上 | — | **保留** |
| `plan-g6-hooks-bridge.md` | **有**：`cc_bridge.py` / `cc_bridge_rules.py` 设计依据路径 | — | **保留** |
| `plan-tier-ontology-layering.md` | **有**：`versioned_ontology_store.py` + tier 测试设计依据 | — | **保留** |
| `Hermes调研底稿.md` | 无（结论在对标主报告） | 调研轨迹 | **迁** `docs/archive/` |
| `LLM自动选择策略审计报告.md` | 无（问题已闭环） | 审计快照 | **迁** `docs/archive/` |
| `记忆系统审计报告.md` | 无操作/验收 MUST | 审计快照 | **迁** `docs/archive/` |

**未删。** 外部留存：**未核实·待确认**（不阻迁 archive）。

## 说明

「已实施」≠ 可退出维护区：应用工厂 L2–L5 设计文被验收契约钉死路径；G6/tier 被生产代码注释引用。若未来要迁出，须先改契约与代码引用（另批）。

## 观测（执行后）

见合理减量方案 §11；`docs/` 树内总数因迁 archive **不变**（仍在 docs 树）。
