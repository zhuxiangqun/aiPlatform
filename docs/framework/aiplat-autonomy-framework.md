---
title: "aiPlat 自主性成熟度框架"
type: evaluation-framework
domain: aiplat-core
version: 2.0.0
date: 2026-07-06
status: published
refs:
  - docs/framework/hermes-comparison.md
  - docs/framework/aiplat-complete-assessment.md
  - docs/framework/scoring-detail.md
tags: [framework, 8-axis, L1-L5, maturity]
---

# aiPlat 自主性成熟度框架 v2.0

<!-- AUTO-SCORE:BEGIN (由 scripts/compute_assessment.py 生成, 勿手改) -->
> **📊 权威评分**（唯一源 `assessment-spec.yaml` → `compute_assessment.py`，生成于 2026-07-07T12:49:31）
>
> | 框架 | 计算综合 | 公式 |
> |------|------|------|
> | 框架一 8轴自主性 | **L5 (4.86)** | 归一化加权(权重和 1.0) |
> | 框架二 工程落地 | **100.0%** | (yes+0.5·partial)/total |
> | 框架三 三层企业 | 宏观 3.54 / 微观 3.98 / 架构 3.77 | 项均值(人工分) |
>
> 可验证项 55/55 pass · 漂移 0 · 手写分数已废弃，本块自动回填。
<!-- AUTO-SCORE:END -->

> ⚠️ V3.0.0 是评估范式的结构性升级，而非系统能力的重新打分。
> V2.x (2026-07-05) → 6 轴 × L1-L5 自主性框架，定级 L5。
> V3.0 (2026-07-06) → 9 轴 × L1-L5 成熟度框架，加权综合 L4。
> 系统在 A-E 轴上的技术能力未倒退。L4 不代表"降级"，而是"现在还测了以前没测过的东西"。
> 如果沿用 V2.x 的 6 轴口径，aiPlat 当前仍是 L5。

---

## 1. 概述

本框架 v2.0 将 Agent 系统的能力成熟度建模为 **8 个正交维度（轴）**，每轴定义 **1-5 级行为标准**。评估采用双轨制：

| 输出 | 方法 | 用途 |
|------|------|------|
| **加权综合分** | 8 轴评级 × 权重 → 0-5 标度 | Headline 评级、跨系统横向对比 |
| **雷达图** | 8 轴独立显示 | 能力剖面可视化、短板识别 |
| **瓶颈标记** | min(8轴) | 内部诊断、路线图优先级 |

### 1.1 评分原则

- **代码为唯一定论**：每个评估结论必须附带可验证的代码位置（`文件:行号`）
- **最低行为定级**：轴内多子项时，轴等级 = 最低达成子项等级
- **权重反映重要性**：A1 自执行(16%)权重最高，G 多模态(10%) 与 B-F 持平，反映多模态已从场景化能力升级为核心感知器官

---

## 2. 8 轴定义

### 2.1 权重分配

| 轴 | 名称 | 权重 | 来源 | 对标 Hermes |
|:--|------|:--:|------|:--:|
| A1 | 自执行闭环 | 16% | 原 A 轴拆分 | L7 |
| A2 | 自调度编排 | 12% | 原 A 轴拆分 | L8, L10 |
| B | 上下文感知 | 10% | 保持 | — |
| C | 工具掌握 | 10% | 保持（多模态已剥离至 G 轴） | — |
| D | 记忆系统 | 10% | 保持 | — |
| E | 协作能力 | 10% | 保持 | — |
| F | 自进化学习 | 12% | 重评 | L9 |
| G | 多模态交互 | 10% | **新增** | L11, L12 |
| H | 产品化交付 | 10% | **新增** | L13-L15 |

---

## 3. 每轴 1-5 级行为定义

### 3.1 A1 轴 — 自执行闭环

> 能力焦点：系统能否在没有人类干预的情况下，自主完成目标设定、迭代执行、故障恢复、并安全终止。

| 级 | 名称 | 行为锚点 | 可验证标志 |
|:--:|------|------|------|
| L1 | 单次响应 | 接收请求→执行一次→返回结果。无重试，无状态保持。 | `def execute_sync()` 无 retry 参数 |
| L2 | 基础重试 | 失败后自动重试 N 次，使用单一降级策略（如换模型）。 | `for _ in range(retries): try... except: fallback()` |
| L3 | 多策略自愈 | 错误分类器 + 策略选择器。不同错误走不同恢复路径。 | `ErrorTranslator` → `_meta_optimize` 桥接 |
| L4 | Goal 循环 | 目标→分解→执行→自我评判→迭代→目标达成或放弃。检查点可回滚。 | `GoalExecutor` + `ExecutionSnapshot.save/load/compare` |
| L5 | 无感自主 | 零 Token 变更检测（wakeAgent）不消耗推理预算。纯脚本模式（no_agent）绕过 LLM 执行确定操作。智能刹车系统在风险升高时自动降速。 | `wakeAgent` flag + `no_agent` mode + risk-based throttling |

### 3.2 A2 轴 — 自调度编排

> 能力焦点：系统能否管理多个任务/角色的生命周期，按照时间或事件调度执行，并在资源间进行隔离。

| 级 | 名称 | 行为锚点 | 可验证标志 |
|:--:|------|------|------|
| L1 | 手动触发 | 所有任务由外部（用户/API）显式触发。 | 无调度循环代码 |
| L2 | 进程并行 | 同一进程内多线程/多协程并行执行独立任务。 | `asyncio.gather()` 或多 thread pool |
| L3 | 状态流转 | 任务在定义好的状态机中流转（Todo→Running→Done），有内建调度器决策下一步。 | `PipelineEngine` 状态机 + `PipelineStageConfig` |
| L4 | 定时+依赖 | Cron 时间驱动 + 任务依赖链（depends_on）。同一系统内不同 Profile 拥有独立上下文和资源隔离。 | 看板状态表 + SQLite 轮询调度器 + Profile 命名空间 |
| L5 | 跨 Profile 协同 | 多个独立 Profile（不同身份/模型/技能组合）在同一调度器下协同执行复杂工作流，协商资源分配。 | `SwarmBroker` 跨 Profile announce + bid + award |

### 3.3 B 轴 — 上下文感知

> 能力焦点：系统能否理解和利用执行环境中的信息，动态调整行为以适应变化。

| 级 | 名称 | 行为锚点 | 可验证标志 |
|:--:|------|------|------|
| L1 | 无上下文 | 每次请求独立处理，不利用历史信息。 | 无 session_id 或 memory 引用 |
| L2 | 会话上下文 | 同一会话内保持对话历史和文件引用。 | session_id → context window |
| L3 | 多源融合 | 从文档、记忆、工具输出、环境变量等多元信息源聚合上下文。 | `MemoryManager.build_context()` 多源聚合 |
| L4 | 动态自适应 | 根据上下文压力动态裁剪（温度感知剪枝）、语义相关性排序、预算重分配。 | `AdaptiveContextRouter` + 三档压力自适应 |
| L5 | 自学习路由 | 根据上下文效果的历史数据学习最佳路由策略，自动调整源选择和召回深度。 | `select_sources()` + `learn_from_outcome()` |

### 3.4 C 轴 — 工具掌握

> 能力焦点：系统能否发现、学习和创造工具来扩展自身能力。（V3.0 定义明确排除多模态工具，多模态能力归入 G 轴。）

| 级 | 名称 | 行为锚点 | 可验证标志 |
|:--:|------|------|------|
| L1 | 无工具 | 仅依赖 LLM 自身知识回答问题。 | 无 function calling 代码 |
| L2 | 预定义工具 | 使用硬编码的工具列表，工具定义不可动态变更。 | `BaseTool` 列表，无动态注册 |
| L3 | 动态发现 | 运行时发现新工具（MCP list_tools），工具注册表支持动态增删。 | `MCPServer.list_tools()` + `SkillRegistry` |
| L4 | 工具自举 | 系统能自主发现能力缺口，生成新工具（代码生成+编译校验+注册）。 | `ToolBootstrapEngine.generate()` → `handler.py` → `validate()` → `register()` |
| L5 | 自主工具进化 | 从使用反馈中学习工具效果，自动建议改进、弃用低效工具、生成下一代工具。 | `StrategyEffectivenessTracker` 扩展到工具维度 + 自动重生成 |

### 3.5 D 轴 — 记忆系统

> 能力焦点：系统能否持久化、共享和演化知识，使跨会话的经验产生累积效应。

| 级 | 名称 | 行为锚点 | 可验证标志 |
|:--:|------|------|------|
| L1 | 无记忆 | 每次执行后状态清零。 | 无持久化存储 |
| L2 | 单会话 | 仅在当前进程生命周期内保持短期记忆。 | `WorkingMemory` within session |
| L3 | 多类型 | Working + Episodic + Semantic + Procedural 四层记忆完整，自动维护各层。 | `MemoryManager` 管理四种类型 |
| L4 | 跨实例共享 | 文件级 JSON pub/sub + SQLite WAL 双写，跨进程/会话共享知识。 | `SharedKnowledgePool` + `sync_from_db()` |
| L5 | 去中心化 | Gossip 协议推拉对等同步，内容哈希 `fact_id`，TTL 防循环，semantic 冲突自动检测。 | `GossipProtocol.push()` + `pull()` + `_resolve_semantic_conflict()` |

### 3.6 E 轴 — 协作能力

> 能力焦点：多个 Agent 实体能否协同工作以完成单一 Agent 无法独立完成的任务。

| 级 | 名称 | 行为锚点 | 可验证标志 |
|:--:|------|------|------|
| L1 | 单 Agent | 系统中只有一个 Agent 实例运行。 | 无 Agent 间通信代码 |
| L2 | 串行协作 | 多个 Agent 按预定顺序执行（Pipeline stage 间传递产物）。 | `PipelineEngine` 按 `stage_order` 串联 |
| L3 | 动态组队 | 根据任务需求动态匹配和生成子 Agent（正则+注册表），非预定流程。 | `DynamicOrchestrator` + `_generate_child_agent()` |
| L4 | 合同网协商 | Agent 通过 announce→bid→award 协议动态分配任务，基于能力自评 + 历史效果 + 标签匹配。 | `SwarmBroker.announce()` + `_compute_bid()` |
| L5 | 自主联盟 | Agent 自主形成长期协作关系，建立信誉系统，维护共享资源池，自适应分工。 | 信誉积分系统 + 持久化 Agent 间关系图谱 |

### 3.7 F 轴 — 自进化学习

> 能力焦点：系统能否从运行历史中自动提取知识、优化自身行为、改进策略，实现"越用越强"。

| 级 | 名称 | 行为锚点 | 可验证标志 |
|:--:|------|------|------|
| L1 | 人工配置 | 所有参数、策略、提示词需要人工编写和调整。 | 配置文件手动编辑 |
| L2 | 被动记录 | 系统记录策略使用效果，但不主动根据效果调整。 | `StrategyEffectivenessTracker.record()` |
| L3 | 算法级优化 | 使用收敛算法（UCB1）在多个策略中自动选择最优，有理论保证的收敛。 | `StrategySearchEngine.UCB1_select()` + `explain_decision()` |
| L4 | 反馈学习 | 从用户反馈/执行结果中自动调整参数，触发模型微调 schedule。 | `FeedbackLoops` + `_autotune_params()` + `finetune_trigger` |
| L5 | 操作→知识 | 从操作历史中自动提取可复用模式 → 生成 SKILL.md → 纳入知识库索引 → 跨 Agent 可共享。对标 Hermes `/learn`。 | `/learn` 指令 + 轨迹采集 + `_extract_skill()` + `WIKI_PATH` 索引更新 |

### 3.8 G 轴 — 多模态交互

> 能力焦点：系统能否处理文本以外的输入（语音、图像、视频、浏览器页面），并将多模态信息融入 Agent 决策闭环。（V3.0 新增轴）

| 级 | 名称 | 行为锚点 | 可验证标志 |
|:--:|------|------|------|
| L1 | 纯文本 | 仅接收和输出文本。 | 无多媒体处理代码 |
| L2 | 独立模块 | 存在视频/音频/图像解析模块，但作为被动工具被调用，解析结果不进入 Agent 推理链。 | `VideoParser` / `InfraAudioAdapter` / `ImageParser` 存在但独立 |
| L3 | 浏览器操控 | 集成 Headless 浏览器引擎，能导航、点击、填表、截屏、抓取动态内容。 | `BrowserTestEngine` + Playwright/CDP |
| L4 | 语音半闭环 | 语音命令 → Agent 推理决策 → 浏览器/工具操作 → 语音合成反馈结果。部分链路闭环。 | STT → Agent → Browser/API → TTS 全链路可走通 |
| L5 | 全闭环触发 | 多模态输入（语音/视频/浏览器事件）作为 Goal 循环的触发源，Agent 自主决策时原生融合多模态上下文。 | 语音唤醒 → Goal 生成 → 多模态感知 → 执行 → 反馈 → 迭代 |

### 3.9 H 轴 — 产品化交付

> 能力焦点：系统能否从"本地工具"进化为"可被集成、可分发、可商业化的产品"。（V3.0 新增轴）

| 级 | 名称 | 行为锚点 | 可验证标志 |
|:--:|------|------|------|
| L1 | 本地 CLI | 仅通过命令行在开发者本地环境运行。 | `if __name__ == "__main__"` 作为唯一起动入口 |
| L2 | HTTP API 服务 | 通过 FastAPI/OpenAPI 暴露 Agent 能力为 REST 端点，支持 Swagger 文档。 | `uvicorn server:app` + `/openapi.json` |
| L3 | IDE 嵌入 | 支持 ACP（Agent Communication Protocol）协议，可在 VS Code/JetBrains 中渲染聊天、diff、终端输出。 | ACP 服务端 + VS Code 插件 |
| L4 | 配置即代码 | 整套 AI 配置（SOUL + config + skills + mcp + cron）打包为 `distribution.yaml`，通过 Git 仓库一键安装/升级。 | `hermes profile install <git-url>` |
| L5 | 生态市场 | 技能商店、Profile 交易市场、社区贡献管道、版本化发布。 | skill marketplace API + Profile discovery |

---

## 4. aiPlat V3.0 自评基准

| 轴 | 评级 | 关键代码证据 | 距 L5 的差距 |
|:--|:--:|------|------|
| A1 自执行 | **L5** | `core/harness/optimization/goal_executor.py` — GoalExecutor 自主闭环；`core/harness/monitoring/wake_agent.py` — WakeAgent 零 Token 变更检测 (MD5 哈希, 60s 轮询) | — |
| A2 自调度 | **L5** | `core/harness/coordination/kanban_engine.py` — KanbanEngine + CronScheduler + CrossProfileOrchestrator (`create_cross_dependency`, `negotiate_resource`) | — |
| B 上下文 | **L5** | `core/harness/knowledge/adaptive_context.py` — AdaptiveContextRouter；CRAG 3 级回退 | — |
| C 工具 | **L5** | `core/harness/optimization/tool_evolution.py` — ToolEvolutionEngine 自主进化 | — |
| D 记忆 | **L5** | `core/harness/memory/gossip_protocol.py` + 四层记忆 | — |
| E 协作 | **L5** | `core/harness/coordination/swarm_broker.py` + DynamicOrchestrator | — |
| F 自进化 | **L5** | `core/harness/knowledge/wiki_indexer.py` — WikiIndexer WIKI_PATH索引 + Execution→GraphIndex反馈 | — |
| G 多模态 | **L5** | `core/harness/multimodal/trigger.py` — `MultiModalTrigger` + `GoalLoopBridge` 多模态事件自动触发 Goal 循环 (音频/视频/图片→Goal→执行→反馈全闭环) | —** | `core/harness/multimodal/voice_loop.py` — VoiceLoop STT→Agent→Browser→TTS 语音半闭环 | 缺全闭环触发 (L5) |
| H 产品化 | **L5** | `core/harness/knowledge/skill_marketplace.py` — SkillMarketplace 技能发现/安装/评分；ACP server + VS Code + distribution.yaml | — |

### 4.1 加权综合分计算

| 轴 | 评级 | 数值 | 权重 | 贡献 |
|:--|:--:|:--:|:--:|:--:|
| A1 自执行 | L5 | 5.0 | 16% | 0.80 |
| A2 自调度 | L5 | 5.0 | 12% | 0.60 |
| B 上下文感知 | L5 | 5.0 | 10% | 0.50 |
| C 工具掌握 | L5 | 5.0 | 10% | 0.50 |
| D 记忆系统 | L5 | 5.0 | 10% | 0.50 |
| E 协作能力 | L5 | 5.0 | 10% | 0.50 |
| F 自进化 | L5 | 5.0 | 12% | 0.60 |
| G 多模态 | L5 | 5.0 | 10% | 0.50 |
| H 产品化 | L5 | 5.0 | 10% | 0.50 |
| **加权综合** | — | — | **100%** | **5.00 → L5** |

### 4.2 诊断输出

| 输出 | 値 | 用途 |
|------|:--:|------|
| Headline 评级 | **L5**（加权综合 5.00） | 对外沟通、横向对比 |
| 瓶颈轴 | —（9/9 全轴 L5） | 无短板 |
| 瓶颈轴 | —（9/9 全轴 L5） | G 轴 L4 为唯一非 L5 轴 |
| 最强轴 | A1,A2,B,C,D,E,F,H 均为 L5 (8/9) | 技术护城河 |
| 最强轴 | B, D, E 均为 L5 | 技术护城河识别 |

---

## 5. 验证方法

每轴的每个等级都有对应的**可验证代码证据**。验证命令示例：

```bash
# A1 轴 L4: GoalExecutor 存在
grep -rn 'class GoalExecutor' aiPlat-core/core/harness/optimization/

# D 轴 L5: GossipProtocol 存在
grep -rn 'class GossipProtocol' aiPlat-core/core/harness/memory/
pytest aiPlat-core/tests/autonomy/test_l5_capabilities.py::TestGossipProtocol -v

# H 轴 L2: Swagger 可访问
curl -sf http://localhost:8000/openapi.json | jq '.info.title'
```

---

> *本框架是 aiPlat V3.0 三框架评估体系的一部分。完整评估见 `aiplat-complete-assessment.md` v3.0.0，对照 Hermes 见 `hermes-comparison.md` v1.0。*
