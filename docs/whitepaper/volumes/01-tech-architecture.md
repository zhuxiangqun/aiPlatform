---
title: "aiPlat 技术架构白皮书"
volume_id: tech-architecture
type: whitepaper-volume
status: generated
generated_at: "2026-10-12T17:28:56Z"
audience: "CTO、架构师、平台工程师"
core_question: "为什么这样设计？边界与权衡是什么？"
priority: P0
source_status: ready
suite: docs/whitepaper/whitepaper-suite.yaml
suite_sha256: "d8a7651f6dd8898264db21d05f14cc69407c182541fcce8abc8aaa9b4714bfb0"
language: zh-CN
---

<!-- volume_stamp id=tech-architecture suite_sha256=d8a7651f6dd8898264db21d05f14cc69407c182541fcce8abc8aaa9b4714bfb0 -->

# aiPlat 技术架构白皮书

> **可再生成分卷** · 权威源见下文清单 · 勿手改能力数/评分/ROI  
> 体系：[`../WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md) · 清单：[`../whitepaper-suite.yaml`](../whitepaper-suite.yaml)  
> 重生成：`python3 scripts/generate_whitepaper_volumes.py`

## 0. 卷册元信息

| 字段 | 值 |
|------|-----|
| 卷 ID | `tech-architecture` |
| 受众 | CTO、架构师、平台工程师 |
| 核心问题 | 为什么这样设计？边界与权衡是什么？ |
| 优先级 | P0 |
| 材料完备度（suite） | `ready` |
| 生成时间 (UTC) | `2026-10-12T17:28:56Z` |

## 1. 本卷论证目标

本卷面向 **CTO、架构师、平台工程师**，围绕「**为什么这样设计？边界与权衡是什么？**」组织既有权威文档。结论与数字以源文件为准；本卷负责受众叙事框架与可读编排。

## 2. 权威源清单（存在性已校验）

### 2.1 Canonical

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/whitepaper/aiplat-platform-status-whitepaper.md`](../aiplat-platform-status-whitepaper.md) | 现状总册（能力全收录，由 CAPABILITIES 生成） | ✅ |
| [`docs/architecture/overview.md`](../architecture/overview.md) | 架构全景唯一入口 | ✅ |
| [`docs/architecture/execution-decision-matrix.md`](../architecture/execution-decision-matrix.md) | 执行选型矩阵 | ✅ |
| [`docs/architecture/plans/pi-thin-runtime.md`](../architecture/plans/pi-thin-runtime.md) | 厂外薄 Runtime 决策边界 | ✅ |
| [`docs/DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md) | 文档权威模型 | ✅ |


### 2.2 Supporting

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/architecture/comparison.md`](../architecture/comparison.md) | 架构层对比 | ✅ |
| [`docs/architecture/plans/comparison.md`](../architecture/plans/comparison.md) | 规划期对比 | ✅ |
| [`CLAUDE.md`](../../CLAUDE.md) | 执行规约 / 层边界 | ✅ |


## 3. 正文编排（节选权威源）

### 3.0 关键设计决策索引

本卷不重抄 ADR 全文，以索引方式消解散落问题。设计决策分散在以下权威源：

| 决策域 | 权威源 |
|--------|--------|
| 平台总览与边界 | [`docs/architecture/overview.md`](../architecture/overview.md) |
| 执行决策矩阵 | [`docs/architecture/execution-decision-matrix.md`](../architecture/execution-decision-matrix.md) |
| Pi 薄运行时 | [`docs/architecture/plans/pi-thin-runtime.md`](../architecture/plans/pi-thin-runtime.md) |
| 文档体系与 ADR 分布 | [`docs/DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md) |

索引维护责任与更新触发条件见 [`docs/whitepaper/WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md)「ADR 索引维护」节。

> 索引只指向权威源，不复制 ADR 正文。修改 overview / execution-decision-matrix / pi-thin-runtime / DOCUMENT_SYSTEM 任一文件时，必须同步本索引。

### 3.1 架构全景（overview）

# aiPlatform 系统架构全景

> 最后更新: 2026-07-04 | 当前能力数见 AIPLAT_CAPABILITIES.md | 从 `AIPLAT_CAPABILITIES.md` 聚合生成
> 
> 本文档是 aiPlat 架构的**唯一全景入口**。5 分钟读懂系统长什么样。
> 零件清单见 CAPABILITIES，详细规约见 CLAUDE.md，对标见 comparison.md。

---

## 一、四层架构

```
┌──────────────────────────────────────────────────────────┐
│ L3: 应用接入层 (app)                                      │
│     前端 UI · 管理端 · Onboarding Wizard · 频道/会话       │
│     aiPlat-management/ · aiPlat-app/                      │
├──────────────────────────────────────────────────────────┤
│ L2: 平台服务层 (platform)                                  │
│     网关 · 鉴权 · 限流 · 路由 · Builder · 知识库           │
│     aiPlat-platform/    依赖方向: ↓ core                  │
├──────────────────────────────────────────────────────────┤
│ L1: AI 核心引擎 (core) ←── 系统心脏                        │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Harness (OS 内核)                                   │  │
│  │   pipeline_engine.py    — 多阶段流水线调度           │  │
│  │   loop.py               — ReAct 执行循环             │  │
│  │   dynamic_router.py     — LLM 动态路由               │  │
│  │   debate/swarm/roundtable — 5种协作模式              │  │
│  ├────────────────────────────────────────────────────┤  │
│  │ 子系统                                               │  │
│  │   memory/       — 四层记忆 (Working→Episodic→Semantic→TaskSkills) │
│  │   knowledge/    — 本体引擎 + Wiki + 图索引 + 域路由           │
│  │   syscalls/     — 唯一外部交互边界 (LLM/Tool/Skill)          │
│  │   learning/     — 自学习 (AutoLearner + SkillEvolver)         │
│  │   ontology_engine/ — 13步认知管线 (Palantir 对齐)            │
│  │   finance/      — 业务价值计算 (5维ROI)                      │
│  │   models/       — SpecLifecycle (版本状态机)                  │
│  ├────────────────────────────────────────────────────┤  │
│  │ 服务层                                               │  │
│  │   apps/agents/  — 7种 Agent 实现类                    │  │
│  │   apps/skills/  — 31 Engine + ~45 Workspace 技能      │  │
│  │   apps/tools/   — 19 内置工具 + MCP 适配              │  │
│  │   apps/mcp/     — MCP 客户端/服务端/运行时             │  │
│  │   management/   — 管理工具 (compliance/lint/adapter)   │  │
│  └────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────┤
│ L0: 基础设施层 (infra)                                    │
│     ModelManager · LLMClient · EmbeddingClient            │
│     Database · Vector · Network · Storage                │
│     aiPlat-infra/    零应用知识                            │
└──────────────────────────────────────────────────────────┘
```

**依赖方向**: `app → platform → core → infra`（严格单向，禁止反向或跨层）

---

## 二、核心数据流

```
User Query
  │
  ▼
┌─ API Router (core/api/routers/) ────────────────────┐
│  鉴权 → 路由到 Service                                │
│  例: POST /submit → workbench.py:submit_task()       │
└──────────────┬──────────────────────────────────────┘
               ▼
┌─ Agent 执行 (apps/agents/) ─────────────────────────┐
│  MaterialsChatAgent / ReActAgent / MultiAgent        │
│  1. DomainRouter.classify() → domain_id             │
│  2. MemoryManager.build_context() → 注入记忆         │
│  3. ReActLoop (harness/execution/loop.py)           │
└──────────────┬──────────────────────────────────────┘
               ▼
┌─ ReAct 循环 (Reason → Act → Observe) ───────────────┐
│  Reason: sys_llm_generate() → LLM 调用               │
│  Act:    sys_tool_call() / sys_skill_call()          │
│  Observe: 结果验证 + CoT 自动注入 + 自纠错            │
│  [14 Hook 阶段可拦截]                                 │
└──────────────┬──────────────────────────────────────┘
               ▼
┌─ 外部交互 (唯一通道: syscalls/) ────────────────────┐
│  sys_llm_generate  → InfraLLMAdapter → LLMClient    │
│  sys_tool_call     → PolicyGate → BaseTool.execute  │
│  sys_skill_call    → SkillExecutor → Skill.execute  │
│  sys_knowledge_retrieve → Wiki + KB + CRAG 回退     │
└─────────────────────────────────────────────────────┘

Pipeline 多阶段执行:
  PipelineEngine → LangGraph(可视化+checkpoint) → StageRunner → ReActLoop
  → [Sandbox: 子进程(Docker可选, --network none)] → HITL 暂停/恢复
  → snapshot → 下一阶段 → 完成 → Skill 晶体化

MCP 交互路径:
  外部 MCP Server → MCPClient (client.py) → sys_tool_call → PolicyGate → Agent 使用工具
  本地工具 → MCPServer (server.py) → 外部 MCP Client 调用 aiPlat 能力

A2A 交互路径:
  外部 Agent → /tasks API (A2A协议) → CoreFacade → Agent 执行 → /tasks/{id} 查询结果/artifact
```

---

## 三、关键架构决策

| # | 决策 | 说明 |
|:---:|------|------|
| 1 | **Harness = OS, Agent = App** | 执行内核不懂业务概念。所有行为分叉来自 `PipelineStageConfig` 字段 |
| 2 | **One Harness, Many Agents** | 7 种 Agent 类型共享一个 ReActLoop 引擎 |
| 3 | **Syscall 边界** | `sys_llm_generate`/`sys_tool_call`/`sys_skill_call` 是唯一外部交互通道 |
| 4 | **4 层记忆 (Hermes 对齐)** | Working→Episodic→Semantic→TaskSkills + 投毒防御 |
| 5 | **CRAG 3 级检索回退** | 本体优先 → FTS5 → HyDE，不可跳过 |
| 6 | **ModelManager 集中化** | infra 是唯一模型目录，core 不自行加载模型 |
| 7 | **5 routing_modes** | static/llm/debate/swarm/roundtable — 配置驱动 |
| 8 | **CI 强制文档同步** | 统计表与章节计数不一致 → CI 阻断 |
| 9 | **SpecLifecycle** | DRAFT→STABLE 6 状态版本演进 (竞品无) |
| 10 | **企业治理** | 多租户 + RBAC + PolicyGate + 15维架构守卫 |

详细规约: `aiPlat-core/CLAUDE.md` §5.1-5.95

---

## 四、子系统速查

| 子系统 | 代码入口 | 核心能力 | 能力数 |
|------|------|------|:---:|
| **Harness 执行** | `harness/execution/pipeline_engine.py` | 多阶段调度 + ReAct循环 + 5种协作 + HITL | 26 |
| **记忆** | `harness/memory/manager.py` | 4层记忆 + 5级压缩 + 投毒防御 + 自动学习 | 17 |
| **知识引擎** | `harness/ontology_engine/engine.py` | 13步本体管线 + GraphIndex + Palantir 对齐 | 20 |
| **RAG 检索** | `harness/knowledge/retriever.py` | CRAG 3级回退 + RRF融合 + DomainRouter | 26 |
| **知识基础设施** | `harness/knowledge/` (embedder/db/graph/repo_map/wiki_fts/cap_health...) | 嵌入/图同步/仓库映射/Wiki FTS5/知识质量/进化 | 28 |
| **Agent 系统** | `apps/agents/` | 7种实现类 + DynamicRouter + SubAgent | 11 |
| **Skill 系统** | `apps/skills/registry.py` | 31 engine + ~45 workspace + 自进化 | 13 |
| **安全与治理** | `harness/security/` + `gates/` | ImmuneMemory + PolicyGate(3层) + CircuitBreaker | 27 |
| **可观测性** | `harness/observability/` | trace/span + Dashboard(含FDE Dashboard 3项) + Prometheus + 全域诊断14项 | 13 |
| **模型管理** | `aiPlat-infra/` + `harness/infrastructure/` | ModelManager + 多Provider + PromptCaching | 13 |
| **学习系统** | `harness/learning/` | AutoLearner + FeedbackRadar + SkillEvolver | 45 |
| **RL 训练** | `harness/training/rl_trainer.py` | RLOO + CodeTestReward + Online Rollout + SFT→RL桥接 | 8 |
| **业务价值** | `harness/finance/value_calculator.py` | 5维ROI + GoalAwareRouter + FDE Dashboard | — |
| **SpecLifecycle** | `harness/models/spec_lifecycle.py` | DRAFT→STABLE 版本状态机 | — |
| **诊断中心** | `api/routers/diagnostics.py` | 25类检查 + 14项全域测试 | — |

完整清单: `AIPLAT_CAPABILITIES.md`（每项标注代码位置）

> 注：业务价值、诊断中心的能力分散在"扩展与学习"(45项)、"管理 & 质量"(20项)章节中。SpecLifecycle 包含在扩展与学习的 45 项内。

---

## 五、数据流关键路径

| 路径 | 参与的子系统 | 入口文件 |
|------|---------|------|
| **用户提问→回答** | API → Agent → ReActLoop → LLM | `loop.py:672` |
| **知识检索** | DomainRouter → WikiRetriever → CRAG → RRF | `retrieval.py:576` |
| **多 Agent 协作** | DynamicRouter → PipelineEngine → Reducer | `pipeline_engine.py:1266` |
| **Spec 迭代** | Onboarding → Task → SpecLifecycle → REVIEW | `spec_lifecycle.py` |
| **自学习** | Failure → AutoLearner → SkillDraft → Simulator → Approval | `learning/__init__.py` |
| **SFT→RL训练** | AutoLearner审批→TrajectoryScorer评分→混合采样→ShareGPT→SFT Job→latest.json→RL(RLOO)→Online Rollout | `training/auto_trigger.py` → `rl_trainer.py` |
| **夜间进化** | EvolutionEngine(13步) → ValueCalc → SFT → SpecHealth | `evolution_engine.py:98` |
| **FDE 仪表板** | SpecLifecycle + FeedbackRadar + TraceVisualizer → Dashboard | `workbench.py:441` |
| **平台能力提升 (碎石路→高速公路)** | Spec promote → Approval Queue → SkillRegistry | `spec_lifecycle.py:promote_to_platform` → `workbench.py:post /promote` |

---

## 六、多系统对标

参见 [`docs/architecture/comparison.md`](comparison.md) — 9 维度 vs Hermes Agent / Claude Code / OpenClaw 深度对比。

---

## 七、从哪里开始读

按时间投入分层：参见 [`docs/README.md`](../README.md)。

> 参见：[私有控制平面 — aiPlat 四层防御体系](articles/private-control-plane.md) 了解更多 PolicyGate/ApprovalGate 的设计细节。


### 3.2 架构对比入口（comparison）

# aiPlat — 四平台深度对标分析

> 生成时间：2026-07-19 | 对标范围：aiPlat △2026-07-19 × Hermes △v0.18.2 × Claude Code △latest × OpenClaw △latest
>
> 数据来源：aiPlat 内部代码（能力计数见 AIPLAT_CAPABILITIES.md）+ 三平台开源仓库（GitHub README + 代码结构分析）

---

## 一、四平台核心定位

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **定位** | 企业 AI 操作系统（本体驱动 FDE） | 自学习个人 AI 助手 | 终端编程 Agent | 个人 AI 助手 |
| **语言** | Python | Python 82% + TS 16% | Python 80% + Shell 14% | TypeScript |
| **GitHub** | 私有仓库 | 217k⭐ · 40.8k fork · 16,243 commits | 138k⭐ · 22.2k fork · 705 commits | 383k⭐ · 80.5k fork · 70,598 commits |
| **协议** | 私有 | MIT | 闭源引擎 + 开源插件 | MIT |
| **版本** | v3.0 (详见 CAPABILITIES.md) | v0.18.2 (2026.7.7) | latest | latest |
| **架构层级** | 8 层（本体语义→知识创造→上下文注入→质量评分→FDE诊断→治理→自演进→编码宪法） | 单体 Agent 结构 | 插件化 Agent（`.claude-plugin/`） | Gateway + Agent + Nodes 三层 |
| **行业定位** | 企业 FDE 交付 + 行业解决方案 | 个人消费者 + 开发者工具 | 专业开发者编程辅助 | 个人消费者 + 社区驱动 |

---

## 二、12 维度关键技术对标

### 维度 1：Harness 执行内核

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **执行循环** | ReAct + Plan-Execute + LangGraph 三模式 | ReAct 循环（推理→行动→观察） | 闭源 Agent 引擎 | Agent 循环 |
| **Hook 系统** | 6 阶段 Hook（PreLoop/PostLoop/PreReasoning/PostReasoning/PreAct/PostObserve） | 事件驱动 Hook | 无公开 Hook | 工具级拦截 |
| **Token 预算** | 5 级压缩（70/80/85/90/99%）+ 温度感知剪枝 + 语义排序 | 上下文压缩（`/compress`） | 自动压缩 | 自动管理 |
| **多终端后端** | 单进程 server | Docker/SSH/Singularity/Modal/Daytona | CLI only | Docker + 本地 |
| **Subagent** | SubagentCoordinator + AgentMessageBus | ✅ 并行工作流 + RPC 零上下文 | ✅ 原生 subagent | ✅ sandbox 隔离 |

**aiPlat 领先项**：Hook 系统粒度 × Token 预算 × LangGraph 集成 × 5 级压缩体系

**aiPlat 可借鉴**：Hermes RPC 零上下文 Subagent 模式（aiPlat subagent 需加载完整上下文）

---

### 维度 2：Agent 系统

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **Agent 类型** | ReAct / Plan-Execute / Conversational / RAG / Multi-Agent / Reflection | ReAct 为主 | 闭源 Agent 引擎 | 可配置 Agent 模式 |
| **多 Agent** | SubagentCoordinator + 消息总线 | Subagent 并行工作流 | 原生 subagent | Multi-agent routing + sandbox |
| **Agent 注册** | AGENT.md frontmatter + Registry 自动发现 | AGENTS.md + skills 目录 | CLAUDE.md | AGENTS.md + SOUL.md + TOOLS.md |
| **身份注入** | tenant/actor/roles 三层头注入 | 用户配置 | OAuth | 用户配置 |
| **消息通道** | ReActLoop REST API | Telegram/Discord/Slack/WhatsApp/Signal/CLI | CLI only | 23 通道（含 WeChat/QQ） |
| **自学习** | ✅ SECI 引擎（S→E→C→I→S 螺旋） | ✅ 闭环学习：自主技能创建→使用中改进 | ❌ | ❌ |

**aiPlat 领先项**：Agent 类型多样性 × 自学习 SECI 引擎 × 三层身份注入

**aiPlat 可借鉴**：OpenClaw 23 通道模型（考虑扩展 FDE 的消息通道）

---

### 维度 3：Skill 系统

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **Skill 定义** | SKILL.md frontmatter + handler.py（Python 类）/ prompt（LLM） | agentskills.io 开放标准 | Custom Commands（`.claude/commands/`） | ClawHub（`skills/<name>/SKILL.md`） |
| **数量** | 44 engine + 21 workspace | 社区 + optional-skills 目录 | ~10 built-in | 社区 + workspace |
| **执行方式** | handler（确定性）+ prompt（LLM 模拟）| prompt + handler | Command 形式 | SKILL.md 形式 |
| **跨平台标准** | 自定义（YAML frontmatter） | ✅ agentskills.io（开放标准） | 自定义 | 自定义 |
| **自主创建** | ✅ ActiveSynthesis + STORM 5步 | ✅ 复杂任务后自动创建技能 | ❌ | ❌ |
| **审计** | ✅ AIPLAT_EXECUTION_AUDIT=true | ❌ | ❌ | ❌ |

**aiPlat 领先项**：执行类型双模式 × 自主创建 × 执行审计

**aiPlat 可借鉴**：Hermes agentskills.io 开放标准（考虑兼容）

---

### 维度 4：MCP 集成

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **MCP 管理** | 统一归属 core/apps/mcp/ + PolicyGate | optional-mcps/ 目录 | MCP Registry 集成 | MCP 工具注册 |
| **工具适配** | MCPToolAdapter（extends BaseTool） | 内置 MCP 客户端 | 内置 MCP 客户端 | 内置 MCP 客户端 |
| **安全** | PolicyGate + ApprovalGate 双重门禁 | DM 配对机制 | 命令审批 | DM 配对 + sandbox |

**aiPlat 领先项**：统一归属 + 双重门禁

---

### 维度 5：记忆系统

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **分层** | 4 层（Working / Episodic / Semantic / Task Skills） | Honcho 对话建模 + FTS5 搜索 | CLAUDE.md 永驻上下文 | SOUL.md + TOOLS.md |
| **搜索** | FTS5 + 嵌入语义 + 跨会话 | FTS5 全文搜索 + LLM 摘要 | 项目级上下文 | 项目级上下文 |
| **长期记忆** | SQLite long_term_memories + 自动过期 | MEMORY.md + USER.md | 会话内 | 会话内 |
| **压缩** | 5 级（70/80/85/90/99%）+ 温度感知 + 语义排序 | 手动 /compress | 自动压缩 | 自动管理 |
| **跨会话** | ✅ 语义记忆续期 + 跨会话召回 | ✅ FTS5 + LLM 摘要 | ⚠️ 单会话 | ⚠️ 单会话 |

**aiPlat 领先项**：4 层架构 × 5 级压缩 × 语义排序 × 跨会话持久化

---

### 维度 6：知识库管理

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **本体驱动** | ✅ YAML 域本体 + GraphIndex + 13步引擎 | ❌ | ❌ | ❌ |
| **向量存储** | ✅ InfraEmbeddingAdapter + FTS5 | 项目文件 | 项目文件 | 项目文件 |
| **知识合成** | ✅ KnowledgeSynthesizer（3 类型） | ❌ | ❌ | ❌ |
| **外部本体导入** | ✅ OWL/SKOS/JSON-LD | ❌ | ❌ | ❌ |
| **域路由** | ✅ DomainRouter 3 层级联 | N/A | N/A | N/A |

**aiPlat 领先项**：本体驱动 × 13步引擎 × 知识合成 × 外部导入 × 域路由

**核心差异**：aiPlat 是本系列中唯一拥有结构化知识引擎的平台。

---

### 维度 7：RAG 检索增强

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **检索模式** | CRAG 3 级回退 + HyDE + Self-RAG | FTS5 全文搜索 + LLM 摘要 | Codebase 搜索 | 工具搜索 |
| **检索融合** | RRF 融合（Wiki + KB + Graph） | 无融合 | 无融合 | 无融合 |
| **质量门** | CRAG（本体优先→FTS5→HyDE）| 无 | 无 | 无 |

**aiPlat 领先项**：CRAG 多级回退 × RRF 融合 × 本体优先路由

---

### 维度 8：提示词工程

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **模板管理** | prompt_loader（`_register()` + `_sync_resolve()`）+ 版本化 | AGENTS.md + skills | CLAUDE.md | AGENTS.md + SOUL.md |
| **注入机制** | 10 层 ContextBus + CLAUDE.md 永驻 | 直接注入 | 直接注入 | 直接注入 |
| **编码宪法** | ✅ karpathy_v1 全局默认 | ❌ | ❌ | ❌ |
| **模板数量** | 65+ 模板 | 无集中管理 | 无集中管理 | 无集中管理 |

**aiPlat 领先项**：模板集中管理 × 编码宪法 × 10 层注入

---

### 维度 9：可观测性

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **追踪** | trace_id/span_id 全链路 | 基本日志 | 基本日志 | 基本日志 |
| **审计** | ✅ usage_tracker + AIPLAT_EXECUTION_AUDIT | ❌ | ❌ | ❌ |
| **OpenTelemetry** | ✅ OTLP（AIPLAT_OTEL_ENABLED） | ❌ | ❌ | ❌ |
| **诊断矩阵** | 37 类检查 + 架构守卫 | ❌ | ❌ | ❌ |

**aiPlat 领先项**：全链路追踪 × 执行审计 × OTEL × 诊断矩阵

---

### 维度 10：幻觉检测与事实核查

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **幻觉检测** | ✅ HallucinationTracker（NLI + Faithfulness） | ❌ | ❌ | ❌ |
| **事实核查** | GraphInference + RRF + Self-RAG | ❌ | ❌ | ❌ |
| **语义缓存** | ✅ L1+L2+L3 语义缓存 | ❌ | ❌ | ❌ |

**aiPlat 领先项**：幻觉检测 × 语义缓存 × 事实核查三层防护

---

### 维度 11：自演进系统

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **自演进引擎** | ✅ SECI 引擎（S→E→C→I→S）+ EvolutionEngine | ❌ | ❌ | ❌ |
| **诊断→修复→演化** | ✅ SystemDiagnostician → Healer → Evolver | ❌ | ❌ | ❌ |
| **反馈闭环** | ✅ FeedbackLoops + CandidatePool + ActiveSynthesis | ✅ 自学习闭环（技能创建→使用中改进） | ❌ | ❌ |
| **Cron 自动化** | ✅ governance cron + learning scheduler | ✅ 自然语言 cron 任务 | ❌ | ✅ cron jobs |

**aiPlat 领先项**：完整的诊断→修复→演化闭环 × SECI 引擎 × 反馈闭环

**Hermes 领先项**：自主技能创建的学习闭环（aiPlat 有 ActiveSynthesis 对标，但执行路径不同）

---

### 维度 12：治理体系（v3.0 新增）

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **本体变更审批** | ✅ OntologyApproval（submit/approve/reject） | ❌ | ❌ | ❌ |
| **治理管线** | ✅ GovernancePipeline（6步循环） | ❌ | ❌ | ❌ |
| **映射验证** | ✅ MappingValidator（类型/枚举/覆盖率） | ❌ | ❌ | ❌ |
| **治理仪表盘** | ✅ 健康总分 + 7 机制状态 + 审批队列 | ❌ | ❌ | ❌ |
| **RBAC 治理角色** | ✅ 4 种治理角色 × 12 种权限 | ❌ | ❌ | ❌ |

**aiPlat 独有**：三平台均无正式的本体治理体系。

---

## 三、aiPlat 体系性领先优势（12 项）

| # | 能力 | 独有程度 |
|:---:|------|:---:|
| 1 | YAML 驱动本体引擎（15 域 × 40+ 模块） | 独有 |
| 2 | 13 步本体引擎管线（12 步确定性 + 1 步 LLM） | 独有 |
| 3 | GraphIndex 双向图 SQLite 存储（含超边 + 快照） | 独有 |
| 4 | DomainRouter 3 层级联（T1 标签 <1ms → T2 嵌入 50ms → T3 LLM 300ms） | 独有 |
| 5 | SECI 知识创造引擎（S→E→C→I→S 螺旋） | 独有 |
| 6 | GovernancePipeline 6 步治理闭环 | 独有 |
| 7 | OntologyAgent 5 步推理编排（理解→规划→查询→评分→输出） | 独有 |
| 8 | ScoringEngine 累加加权评分（via_path 多跳 + 阈值按成熟度自适应） | 独有 |
| 9 | PathPlanner 目标导向路径规划（预定义模板 + 自动发现 fallback） | 独有 |
| 10 | ScenarioSelector 4 象限场景优先级（5 条件评估） | 独有 |
| 11 | 4 层记忆体系（Working + Episodic + Semantic + Task Skills） | 群领先 |
| 12 | 5 级上下文压缩（温度感知 + 语义排序 + 跨层重排） | 群领先 |

---

## 四、从三平台可借鉴的能力

| 来源 | 能力 | 借鉴价值 | 对 aiPlat 的建议 |
|:---|------|:---:|------|:---:|
| **Claude Code** | Custom Commands 斜杠命令 | 高 | AGENT.md `commands:` frontmatter + `command_parser.py` | ✅ 已实现 |
| **OpenClaw** | FDE 消息通知接线 | 高 | `fde_notifier.py` → 飞书/企微/Slack | ✅ 已实现 |
| **OpenClaw** | Sandbox 接线 PipelineEngine | 高 | `pipeline_engine.py` + `SandboxGate` 预检 | ✅ 已实现 |
| **Hermes** | Subagent RPC 零上下文调用 | 高 | `multi_agent.py` `_build_task_context()` | ✅ 已实现 |
| **OpenClaw** | Live Canvas（推理链可视化） | 高 | `ReasoningTracePanel.tsx` + FdeDashboard | ✅ 已实现 |
| **Hermes** | agentskills.io Skill 开放标准 | 高 | 考虑兼容（当前格式更丰富，延迟评估） | P3 |
| **Hermes** | 多终端后端（Modal/Daytona serverless） | 中 | 企业私有部署模型不适用 | P3 |
| **Claude Code** | Plugin 系统（`.claude-plugin/`） | 中 | Skill+MCP+Tool+Hook 已覆盖，Plugin 为语法糖 | P2 |
| **Claude Code** | Custom Commands（`.claude/commands/`） | 中 | 已通过 AGENT.md `commands:` 实现 | ✅ |
| **OpenClaw** | 23 通道消息网关 | 中 | 已有 3 通道（飞书/企微/Slack），FDE 已接线 | ✅ | |

---

## 五、综合评分矩阵

| 维度 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---:|:---:|:---:|:---:|
| 1. Harness 执行内核 | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★☆☆ |
| 2. Agent 系统 | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★★☆ |
| 3. Skill 系统 | ★★★★★ | ★★★★★ | ★★★☆☆ | ★★★★☆ |
| 4. MCP 集成 | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★★☆ |
| 5. 记忆系统 | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★☆☆ |
| 6. 知识库管理 | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| 7. RAG 检索 | ★★★★★ | ★★★☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| 8. 提示词工程 | ★★★★★ | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ |
| 9. 可观测性 | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| 10. 幻觉检测 | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| 11. 自演进系统 | ★★★★★ | ★★★☆☆ | ★☆☆☆☆ | ★☆☆☆☆ |
| 12. 治理体系 | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ | ★☆☆☆☆ |
| **加权总分** | **98** | **68** | **55** | **52** |

---

*对标基准日期：aiPlat 2026-07-19 (v3.0) · Hermes 2026-07-08 (v0.18.2) · Claude Code 2026-07 · OpenClaw 2026-07*
*权重：维度 1,2,3,5 各 10%；维度 6,7,8,11 各 8%；维度 4,9,10,12 各 7%*


## 4. 相关横切（对标 / 评级）

完整对标与评级目录见总白皮书 §2.5 与 [`docs/whitepaper/WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md)。

## 5. 验证

```bash
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check
```

*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`tech-architecture`*
