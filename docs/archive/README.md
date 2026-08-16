# 历史文档归档

> 存档时间: 2026-07-01  
> 原因: 文档精简 — 合并重复文档，淘汰过期文档  

**重要声明：归档内容仅做历史参考，不构成当前系统的约束。如有冲突，以 `docs/architecture/` 和 `CLAUDE.md` 为准。**

## 归档文件

| 文件 | 原因 |
|------|------|
| `aiPlat_arch_vs_hermes.md` | 合并入 `docs/architecture/comparison.md`；历史对比，已被 `docs/research/aiPlat核心能力对标报告.md` 取代 |
| `架构对照-aiPlat-vs-Hermes-vs-ClaudeCode-vs-OpenClaw.md` | 同上；已被 `docs/research/aiPlat核心能力对标报告.md` 取代 |
| `aiPlat-vs-hermes-vs-claude-code-vs-openclaw-architecture.md` | 同上；已被 `docs/research/aiPlat核心能力对标报告.md` 取代 |
| `AIPLAT_WHITEPAPER.md` | 内容过期，被 CAPABILITIES + ROADMAP 覆盖 |
| `aiPlat_设计文档与实现一致性审查报.md` | 单次审查报告，快照已过时 |
| `multi_agent_reliability_mapping.md` | 内容已整合入架构对标 |
| `agentstack-implementation-compare.md` | 合并入 `docs/architecture/comparison.md` |
| `aiPlat-17dim-comparison-v3.md` | 被 v4 替代 + 内容已整合入 comparison.md；已被 `docs/research/aiPlat核心能力对标报告.md` 取代 |
| `aiPlat-22dim-comparison-v4.md` | 内容已整合入 comparison.md；已被 `docs/research/aiPlat核心能力对标报告.md` 取代 |
| `aiPlat-architecture-compare.md` | 内容已整合入 comparison.md |
| `multi-dimension-comparison.md` | Dify/Coze/aiPlat 历史对比；已被 `docs/research/aiPlat核心能力对标报告.md` 取代 |
| `2026年路线图归档说明.md` | 2026 年及更早路线图归档索引 |
| `DATABASE_INTEGRATION_REPORT.md` | 数据库集成测试完成报告（历史 As-Is 快照） |
| `INTEGRATION_TESTS_SUMMARY.md` | 集成测试完成总结（历史 As-Is 快照） |
| `MESSAGING_INTEGRATION_REPORT.md` | Messaging 模块集成测试完成报告（历史 As-Is 快照） |
| `TESTCONTAINERS_FINAL_REPORT.md` | Testcontainers 集成测试完成报告（历史 As-Is 快照） |
| `doc_full_scan_report.md` | 文档一致性全量扫描报告（历史快照，单次执行结果） |
| `Roadmap-全量目标-Gap清单.md` | 基于 aiPlat_arch_vs_hermes 的全量目标 Gap 清单（历史） |
| `agent_platform_execution_plan.md` | 基于差距评分表的可执行落地计划（历史规划） |
| `agent_platform_gap_analysis.md` | 对标 OpenClaw/Hermes/Superagent 差距评分表初版（历史） |
| `aiPlat-remaining-checklist.md` | aiPlat Remaining Checklist（MVP 达成快照） |
| `implementation-checklist.md` | aiPlat 改进实施 Checklist（历史过程文档） |
| `p3-17-effect-ts-di-research.md` | P3-17 Effect-TS Layer DI 技术调研（单点研究，无后续接线） |
| `workflow-canvas-comparison.md` | aiPlat vs Dify vs Coze Workflow Canvas 对比（历史，并入 multi-dimension-comparison 定位） |
| `平台化路线-PR拆解与排期.md` | 平台化（多租户/企业）路线 PR 拆解与排期（历史规划） |
| `平台化路线-四服务版PR拆解与排期.md` | 平台化路线四服务版 PR 拆解与排期（历史规划，被实际演进取代） |

> **P1-B6 归档说明（2026-08-16）**：上表 6 份历史对比文档（`aiPlat_arch_vs_hermes` / `架构对照-...` / `aiPlat-vs-hermes-vs-claude-code-vs-openclaw-architecture` / `aiPlat-17dim-comparison-v3` / `aiPlat-22dim-comparison-v4` / `multi-dimension-comparison`）的定位已由 **`docs/research/aiPlat核心能力对标报告.md`**（21 章，Claude Code / DeepSeek Harness / Hermes 核心能力对标）取代。本组文档仅作历史参考。

## 当前活跃文档

- `AIPLAT_CAPABILITIES.md` — 唯一能力真相源
- `AIPLAT_ROADMAP.md` — 路线图 + 评分
- `AIPLAT_ARCHITECTURE_REPORT.md` — 架构分析
- `AIPLAT_DIAGNOSTIC_REPORT.md` — 诊断快照
- `CLAUDE.md` — 工作区 AI 编程规约
- `docs/architecture/comparison.md` — 多系统对标
- `docs/standards/` — 代码规范
- `docs/harness/README.md` → `aiPlat-core/docs/harness/` — 执行引擎详细设计
