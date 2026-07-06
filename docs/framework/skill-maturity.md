---
title: "aiPlat Skill 构建成熟度框架"
type: evaluation-framework
domain: aiplat-core
version: 1.0.0
date: 2026-07-06
status: published
refs:
  - docs/framework/aiplat-autonomy-framework.md
  - docs/framework/aiplat-complete-assessment.md
  - docs/framework/hermes-comparison.md
tags: [framework, skill-maturity, L1-L5, 5-level]
---

# aiPlat Skill 构建成熟度框架 v1.0

> **框架四**：评估 Skill 体系的工程化成熟度。与 8 轴自主性正交——一个 L5 自主性的系统，Skill 构建成熟度可能只有 L3。

---

## 1. 背景

大模型应用正在从"对话式问答"向"技能式执行"演进。Skill 构建能力是 Agent 平台的核心竞争力之一。本框架定义了 Skill 体系从单文件到闭环操作系统的五级成熟度路径。

本框架参考业界 Skill 构建十层模型，压缩为与 aiPlat 八轴一致的 L1-L5 体系，便于统一评估语言。

### 原文十层 → 本框架五级映射

| 原文层级 | 本框架 |
|:--:|:--:|
| L1 纯提示词Skill | L1 单文件Skill |
| L2 组件Skill | L2 组件Skill |
| L3 工作流Skill | L3 工作流Skill |
| L4 编排Skill | L3 工作流Skill（压缩） |
| L5 安全Skill | L4 编排Skill |
| L6 评分Skill | L4 编排Skill |
| L7 验证Skill | L4 编排Skill |
| L8 审批Skill | L4 编排Skill |
| L9 组合Skill | L5 闭环Skill体系 |
| L10 闭环Skill | L5 闭环Skill体系 |

---

## 2. 五级定义

### L1 — 单文件 Skill

**核心特征**：仅有 SKILL.md，纯提示词驱动。无外部资源、无脚本、无参考资料。

**判断标准**：Skill 目录只有 1 个 .md 文件。

**对标原文**：L1 纯提示词Skill

---

### L2 — 组件 Skill

**核心特征**：SKILL.md + references/ + scripts/ + assets/ 多文件结构。AI 执行时可查阅参考文档、调用脚本、使用模板。

**典型实例**：autoreview Skill（8 文件 — handler.py + presets.yaml + references）

**判断标准**：Skill 目录 ≥3 个文件。

**对标原文**：L2 组件Skill

---

### L3 — 工作流 Skill

**核心特征**：多步骤决策树 + 条件分支 + 步骤间数据传递。SKILL.md 含 Workflow 段，每步有前置条件和输出物。PipelineEngine 原生支持多 stage 串联。

**典型实例**：Pipeline 中串联的 code_gen → test_gen → review stages

**判断标准**：SKILL.md 含 Workflow 段 + 条件逻辑，或多 stage 通过 PipelineStageConfig 串联。

**对标原文**：L3 工作流Skill + L4 编排Skill（压缩）

---

### L4 — 编排 Skill

**核心特征**：使用 DynamicOrchestrator 或 SwarmBroker 调度 ≥2 个 sub-Agent 协同工作。具备安全声明（effects full coverage）、YAML 配置驱动评分或证据链验证能力。配置与代码分离——业务人员改 YAML 不改 Skill 代码。

**典型实例**：scoring_template（YAML 驱动评分）+ evidence_chain（多源验证）

**判断标准**：使用 Orchestrator 调度 sub-Agent + YAML 配置驱动。

**对标原文**：L5 安全Skill + L6 评分Skill + L7 验证Skill + L8 审批Skill（压缩）

---

### L5 — 闭环 Skill 体系

**核心特征**：8+ Skill 协同覆盖端到端业务闭环。全量 effects 安全声明（32/32 覆盖）+ 评分/证据链模板可用 + 自进化（/learn）接入 + 可观测（全链审计）。

**典型实例**：EvolutionEngine 夜间 13 步 pipeline + AutoLearner 自动生成 SkillDraft + WikiIndexer WIKI_PATH 索引

**判断标准**：effects 全覆盖 + 评分/证据链模板 + 夜间进化接入。

**对标原文**：L9 组合Skill + L10 闭环Skill

---

## 3. 五级总览

| 级 | 名称 | 核心特征 | 对标原文 | 判断标准 |
|:--:|------|------|:--:|------|
| L1 | 单文件Skill | 仅有 SKILL.md | L1 | 目录只有 1 个 .md |
| L2 | 组件Skill | SKILL.md + references/scripts | L2 | 目录 ≥3 个文件 |
| L3 | 工作流Skill | 多步骤决策树 + 条件分支 | L3-L4 | 含 Workflow 段或多 stage 串联 |
| L4 | 编排Skill | Orchestrator + YAML 配置驱动 | L5-L8 | ≥2 sub-Agent + 配置分离 |
| L5 | 闭环Skill体系 | 8+Skill + 全量安全声明 + 自进化 | L9-L10 | effects 全覆盖 + 进化接入 |

---

## 4. aiPlat 自评基准

| 级 | 证据 | 状态 |
|:--:|------|:--:|
| L1 | 32 个 engine Skill 全量 SKILL.md | ✅ |
| L2 | autoreview 8 文件（handler.py + presets.yaml + references） | ✅ |
| L3 | PipelineEngine 多 stage 串联 + _retry_loop 6 种退出 + 条件分支 | ✅ |
| L4 | DynamicOrchestrator + SwarmBroker + scoring_template + evidence_chain | ✅ |
| L5 | effects 全覆盖 (32/32) + scoring_template + evidence_chain + EvolutionEngine + WikiIndexer | ✅ |

**定级：L5**

---

## 5. 四框架统一视图

| 框架 | 评估对象 | 定级 |
|------|------|:--:|
| 8 轴自主性 | Agent 多聪明/多自主 | L5 (5.00) |
| 工程落地 | 能不能持续交付 | 准生产级 (88.2%) |
| 三层企业 | 有多好 | 基础级 (3.3) |
| **Skill 构建成熟度** | **Skill 体系多成熟** | **L5** |

---

## 6. 与 Hermes 对标

| 维度 | aiPlat | Hermes (估) | 对比 |
|------|:--:|:--:|:--:|
| 单文件Skill | L1 ✅ | L1-L3 | 持平 |
| 组件Skill | L2 ✅ | L2-L3 | 持平 |
| 工作流Skill | L3 ✅ | L3 | 持平 |
| 编排Skill | L4 ✅ | L4-L8 | 持平 |
| 闭环Skill体系 | L5 ✅ | L9-L10 | 持平 |

**结论**：aiPlat Skill 构建成熟度与 Hermes 对齐。

---

## 7. 升级路径

| 优先级 | 目标 | 状态 |
|:--:|------|:--:|
| P0 | effects 校验升级（WARNING → ERROR） | ✅ 已完成 (Phase 71) |
| P1a | 评分引擎 Skill 模板（scoring_template） | ✅ 已完成 (Phase 71) |
| P1b | 证据链 Skill 模板（evidence_chain） | ✅ 已完成 (Phase 71) |
| P2 | 框架四文档 | ✅ 已完成 (Phase 71) |

---

*本框架是 aiPlat 四框架评估体系的一部分。与 8 轴自主性正交，共同构成完整成熟度画像。*
