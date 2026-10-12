---
title: "aiPlat 技术架构白皮书"
volume_id: tech-architecture
type: whitepaper-volume
status: generated
generated_at: "2026-10-12T23:15:53Z"
audience: "CTO、架构师、平台工程师"
core_question: "为什么这样设计？边界与权衡是什么？"
priority: P0
source_status: ready
suite: docs/whitepaper/whitepaper-suite.yaml
suite_sha256: "3d143bcd3a67f7e55f869d4a1a179a2c8bd180756e2e4a0cfea666da8358288e"
caps_sha256: "e2e1936484e9ca34a1fedaa4193db677b76758c50291c870feca845ce034fc94"
scores_sha256: "96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687"
language: zh-CN
---

<!-- volume_stamp id=tech-architecture suite_sha256=3d143bcd3a67f7e55f869d4a1a179a2c8bd180756e2e4a0cfea666da8358288e caps_sha256=e2e1936484e9ca34a1fedaa4193db677b76758c50291c870feca845ce034fc94 scores_sha256=96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687 -->

# aiPlat 技术架构白皮书

> **可再生成分卷** · 权威源见下文清单 · 勿手改能力数/评分/ROI  
> 体系：[`../WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md) · 清单：[`../whitepaper-suite.yaml`](../whitepaper-suite.yaml)  
> 重生成：`bash scripts/sync_whitepapers.sh` 或 `python3 scripts/generate_whitepaper_volumes.py`

## 0. 卷册元信息

| 字段 | 值 |
|------|-----|
| 卷 ID | `tech-architecture` |
| 受众 | CTO、架构师、平台工程师 |
| 核心问题 | 为什么这样设计？边界与权衡是什么？ |
| 优先级 | P0 |
| 材料完备度（suite） | `ready` |
| 生成时间 (UTC) | `2026-10-12T23:15:53Z` |
| CAPABILITIES sha256 | `e2e1936484e9…` |
| assessment-scores sha256 | `96d06b3ea6cd…` |

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
| [`docs/manuals/deployment.md`](../manuals/deployment.md) | 部署与运维视图 | ✅ |
| [`docs/architecture/plans/disaster-recovery-plan.md`](../architecture/plans/disaster-recovery-plan.md) | 灾备 / RPO·RTO | ✅ |
| [`docs/standards/规范-性能.md`](../standards/规范-性能.md) | 性能预算与扩展约束 | ✅ |
| [`docs/architecture/slo.md`](../architecture/slo.md) | SLI/SLO / 误差预算 | ✅ |
| [`docs/architecture/plans/observability-eval-repair-architecture.md`](../architecture/plans/observability-eval-repair-architecture.md) | 可观测性架构 | ✅ |
| [`docs/standards/规范-core-run_id-trace_id-request_id.md`](../standards/规范-core-run_id-trace_id-request_id.md) | run/trace/request id 关联规范 | ✅ |
| [`docs/knowledge-system.md`](../knowledge-system.md) | 数据 / 知识存储路径 | ✅ |
| [`docs/architecture/knowledge-base-architecture.md`](../architecture/knowledge-base-architecture.md) | 知识库架构（已合并指针） | ✅ |
| [`docs/security/security-architecture.md`](../security/security-architecture.md) | 安全嵌入（技术视角交叉） | ✅ |
| [`docs/manuals/testing.md`](../manuals/testing.md) | 测试金字塔与策略 | ✅ |
| [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md) | 执行质量门禁 | ✅ |
| [`AIPLAT_ROADMAP.md`](../../AIPLAT_ROADMAP.md) | 路线与风险（非财务） | ✅ |
| [`docs/research/architecture-evolution-roadmap.md`](../research/architecture-evolution-roadmap.md) | 架构演进路线 | ✅ |
| [`docs/manuals/getting-started.md`](../manuals/getting-started.md) | 开发上手 | ✅ |
| [`docs/architecture/plans/app-module-layout.md`](../architecture/plans/app-module-layout.md) | 应用模块目录规范 | ✅ |
| [`docs/mcp/index.md`](../mcp/index.md) | 集成 / MCP 入口 | ✅ |
| [`docs/policy/mcp-stdio-prod-allowlist.md`](../policy/mcp-stdio-prod-allowlist.md) | MCP stdio 生产允许列表 | ✅ |


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

### aiPlatform 系统架构全景

> 最后更新: 2026-07-04 | 当前能力数见 AIPLAT_CAPABILITIES.md | 从 `AIPLAT_CAPABILITIES.md` 聚合生成
> 
> 本文档是 aiPlat 架构的**唯一全景入口**。5 分钟读懂系统长什么样。
> 零件清单见 CAPABILITIES，详细规约见 CLAUDE.md，对标见 comparison.md。

---

#### 一、四层架构

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

#### 二、核心数据流

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

#### 三、关键架构决策

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

#### 四、子系统速查

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

#### 五、数据流关键路径

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

#### 六、多系统对标

参见 [`docs/architecture/comparison.md`](comparison.md) — 9 维度 vs Hermes Agent / Claude Code / OpenClaw 深度对比。

---

#### 七、从哪里开始读

按时间投入分层：参见 [`docs/README.md`](../README.md)。

> 参见：[私有控制平面 — aiPlat 四层防御体系](articles/private-control-plane.md) 了解更多 PolicyGate/ApprovalGate 的设计细节。


### 3.2 架构对比入口（comparison）

### aiPlat — 四平台深度对标分析

> 生成时间：2026-07-19 | 对标范围：aiPlat △2026-07-19 × Hermes △v0.18.2 × Claude Code △latest × OpenClaw △latest
>
> 数据来源：aiPlat 内部代码（能力计数见 AIPLAT_CAPABILITIES.md）+ 三平台开源仓库（GitHub README + 代码结构分析）

---

#### 一、四平台核心定位

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

#### 二、12 维度关键技术对标

##### 维度 1：Harness 执行内核

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

##### 维度 2：Agent 系统

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

##### 维度 3：Skill 系统

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

##### 维度 4：MCP 集成

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **MCP 管理** | 统一归属 core/apps/mcp/ + PolicyGate | optional-mcps/ 目录 | MCP Registry 集成 | MCP 工具注册 |
| **工具适配** | MCPToolAdapter（extends BaseTool） | 内置 MCP 客户端 | 内置 MCP 客户端 | 内置 MCP 客户端 |
| **安全** | PolicyGate + ApprovalGate 双重门禁 | DM 配对机制 | 命令审批 | DM 配对 + sandbox |

**aiPlat 领先项**：统一归属 + 双重门禁

---

##### 维度 5：记忆系统

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **分层** | 4 层（Working / Episodic / Semantic / Task Skills） | Honcho 对话建模 + FTS5 搜索 | CLAUDE.md 永驻上下文 | SOUL.md + TOOLS.md |
| **搜索** | FTS5 + 嵌入语义 + 跨会话 | FTS5 全文搜索 + LLM 摘要 | 项目级上下文 | 项目级上下文 |
| **长期记忆** | SQLite long_term_memories + 自动过期 | MEMORY.md + USER.md | 会话内 | 会话内 |
| **压缩** | 5 级（70/80/85/90/99%）+ 温度感知 + 语义排序 | 手动 /compress | 自动压缩 | 自动管理 |
| **跨会话** | ✅ 语义记忆续期 + 跨会话召回 | ✅ FTS5 + LLM 摘要 | ⚠️ 单会话 | ⚠️ 单会话 |

**aiPlat 领先项**：4 层架构 × 5 级压缩 × 语义排序 × 跨会话持久化

---

##### 维度 6：知识库管理

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

##### 维度 7：RAG 检索增强

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **检索模式** | CRAG 3 级回退 + HyDE + Self-RAG | FTS5 全文搜索 + LLM 摘要 | Codebase 搜索 | 工具搜索 |
| **检索融合** | RRF 融合（Wiki + KB + Graph） | 无融合 | 无融合 | 无融合 |
| **质量门** | CRAG（本体优先→FTS5→HyDE）| 无 | 无 | 无 |

**aiPlat 领先项**：CRAG 多级回退 × RRF 融合 × 本体优先路由

---

##### 维度 8：提示词工程

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **模板管理** | prompt_loader（`_register()` + `_sync_resolve()`）+ 版本化 | AGENTS.md + skills | CLAUDE.md | AGENTS.md + SOUL.md |
| **注入机制** | 10 层 ContextBus + CLAUDE.md 永驻 | 直接注入 | 直接注入 | 直接注入 |
| **编码宪法** | ✅ karpathy_v1 全局默认 | ❌ | ❌ | ❌ |
| **模板数量** | 65+ 模板 | 无集中管理 | 无集中管理 | 无集中管理 |

**aiPlat 领先项**：模板集中管理 × 编码宪法 × 10 层注入

---

##### 维度 9：可观测性

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **追踪** | trace_id/span_id 全链路 | 基本日志 | 基本日志 | 基本日志 |
| **审计** | ✅ usage_tracker + AIPLAT_EXECUTION_AUDIT | ❌ | ❌ | ❌ |
| **OpenTelemetry** | ✅ OTLP（AIPLAT_OTEL_ENABLED） | ❌ | ❌ | ❌ |
| **诊断矩阵** | 37 类检查 + 架构守卫 | ❌ | ❌ | ❌ |

**aiPlat 领先项**：全链路追踪 × 执行审计 × OTEL × 诊断矩阵

---

##### 维度 10：幻觉检测与事实核查

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **幻觉检测** | ✅ HallucinationTracker（NLI + Faithfulness） | ❌ | ❌ | ❌ |
| **事实核查** | GraphInference + RRF + Self-RAG | ❌ | ❌ | ❌ |
| **语义缓存** | ✅ L1+L2+L3 语义缓存 | ❌ | ❌ | ❌ |

**aiPlat 领先项**：幻觉检测 × 语义缓存 × 事实核查三层防护

---

##### 维度 11：自演进系统

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **自演进引擎** | ✅ SECI 引擎（S→E→C→I→S）+ EvolutionEngine | ❌ | ❌ | ❌ |
| **诊断→修复→演化** | ✅ SystemDiagnostician → Healer → Evolver | ❌ | ❌ | ❌ |
| **反馈闭环** | ✅ FeedbackLoops + CandidatePool + ActiveSynthesis | ✅ 自学习闭环（技能创建→使用中改进） | ❌ | ❌ |
| **Cron 自动化** | ✅ governance cron + learning scheduler | ✅ 自然语言 cron 任务 | ❌ | ✅ cron jobs |

**aiPlat 领先项**：完整的诊断→修复→演化闭环 × SECI 引擎 × 反馈闭环

**Hermes 领先项**：自主技能创建的学习闭环（aiPlat 有 ActiveSynthesis 对标，但执行路径不同）

---

##### 维度 12：治理体系（v3.0 新增）

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **本体变更审批** | ✅ OntologyApproval（submit/approve/reject） | ❌ | ❌ | ❌ |
| **治理管线** | ✅ GovernancePipeline（6步循环） | ❌ | ❌ | ❌ |
| **映射验证** | ✅ MappingValidator（类型/枚举/覆盖率） | ❌ | ❌ | ❌ |
| **治理仪表盘** | ✅ 健康总分 + 7 机制状态 + 审批队列 | ❌ | ❌ | ❌ |
| **RBAC 治理角色** | ✅ 4 种治理角色 × 12 种权限 | ❌ | ❌ | ❌ |

**aiPlat 独有**：三平台均无正式的本体治理体系。

---

#### 三、aiPlat 体系性领先优势（12 项）

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

#### 四、从三平台可借鉴的能力

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

#### 五、综合评分矩阵

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


### 3.3 工程落地视图（索引 + 正文）

本卷在「为什么这样设计」之外，提供部署 / 性能 / 可观测 / 数据 / 安全嵌入 / 测试 / 风险演进 / 开发 / 集成 / SLA 的**索引表 + 权威源正文节选**。节选随权威源再生，**禁止在卷内手写第二份工程全文或编造 QPS/ROI**；完整细节以链接目标为准。

#### 3.3.0 工程维度索引

| 工程维度 | 读者要回答的问题 | 权威源（优先） | CAPABILITIES / 姊妹卷 | 正文节 |
|----------|------------------|----------------|----------------------|--------|
| **部署与运维** | 生产怎么布？环境/灾备/灰度？ | [`docs/manuals/deployment.md`](../manuals/deployment.md) · [`docs/architecture/plans/disaster-recovery-plan.md`](../architecture/plans/disaster-recovery-plan.md) · `deploy/helm/aiplat/` | CAPABILITIES「部署与运维 / 部署与灰度」 | §3.3.1 |
| **性能与扩展** | QPS/P95/容量/扩展策略？ | [`docs/standards/规范-性能.md`](../standards/规范-性能.md) · [`docs/architecture/slo.md`](../architecture/slo.md) · `scripts/benchmark_all.sh` | CAPABILITIES「部署与运维」基准条目 | §3.3.2 |
| **可观测性** | 日志/指标/追踪怎么采与告警？ | [`docs/architecture/plans/observability-eval-repair-architecture.md`](../architecture/plans/observability-eval-repair-architecture.md) · [`docs/standards/规范-core-run_id-trace_id-request_id.md`](../standards/规范-core-run_id-trace_id-request_id.md) | CAPABILITIES「可观测性」· 安全卷可交叉 | §3.3.3 |
| **数据架构** | 存什么、隔离、备份？ | [`docs/knowledge-system.md`](../knowledge-system.md) · [`docs/architecture/knowledge-base-architecture.md`](../architecture/knowledge-base-architecture.md) | CAPABILITIES「知识引擎」· 灾备计划（备份） | §3.3.4 |
| **安全嵌入视图** | Gate/信任边界如何嵌进运行时？ | [`docs/security/security-architecture.md`](../security/security-architecture.md) | 分卷 05 · CAPABILITIES「安全与治理 / Gate」 | §3.3.5 |
| **测试与验证** | 金字塔 / CI / 质量门？ | [`docs/manuals/testing.md`](../manuals/testing.md) · [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md) · `.github/workflows/` | CAPABILITIES「管理 & 质量」 | §3.3.6 |
| **技术风险与演进** | 技术债、依赖风险、路线？ | [`AIPLAT_ROADMAP.md`](../../AIPLAT_ROADMAP.md) · [`docs/research/architecture-evolution-roadmap.md`](../research/architecture-evolution-roadmap.md) · [`CLAUDE.md`](../../CLAUDE.md) §16 | 商业卷 ROADMAP 节选（非财务） | §3.3.7 |
| **开发视图** | 代码组织、模块边界、上手？ | [`CLAUDE.md`](../../CLAUDE.md) · [`docs/DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md) · [`docs/manuals/getting-started.md`](../manuals/getting-started.md) · [`docs/architecture/plans/app-module-layout.md`](../architecture/plans/app-module-layout.md) | — | §3.3.8 |
| **集成架构** | MCP/A2A/外部适配？ | [`docs/mcp/index.md`](../mcp/index.md) · [`docs/policy/mcp-stdio-prod-allowlist.md`](../policy/mcp-stdio-prod-allowlist.md) | 分卷 04 · CAPABILITIES「MCP / A2A」 | §3.3.9 |
| **质量属性 / SLA·SLO** | 可用性目标与误差预算？ | [`docs/architecture/slo.md`](../architecture/slo.md) · [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md) | CAPABILITIES「管理 & 质量」 | §3.3.10 |

> **阅读约定**：索引指路；各 §3.3.x 为权威源节选（可再生）。性能容量以规范预算 + `benchmark_all.sh` + SLO 实测表为准，勿在卷外另抄一套数字。

#### 3.3.1 部署与运维

**尽调问题**：生产拓扑、环境隔离、Helm/灰度、灾备与配置如何落地？

物理/部署视图以手册与 Helm chart 为准；灾备 RPO/RTO 见计划文档。

**权威源**： [`docs/manuals/deployment.md`](../manuals/deployment.md) · [`docs/architecture/plans/disaster-recovery-plan.md`](../architecture/plans/disaster-recovery-plan.md) · `deploy/helm/aiplat/`

**节选自** [`docs/manuals/deployment.md`](../manuals/deployment.md)：

### AI Platform 部署指南

> 系统级部署指南 - 各层必须遵循

---

#### 📋 目录

- [部署架构](#部署架构)
- [环境管理](#环境管理)
- [部署顺序](#部署顺序)
- [部署方式](#部署方式)
- [配置管理](#配置管理)
- [监控告警](#监控告警)
- [日志管理](#日志管理)
- [备份恢复](#备份恢复)
- [故障排查](#故障排查)
- [安全加固](#安全加固)

---

#### 部署架构

##### 整体架构

```
                         ┌─────────────────────┐
                         │   负载均衡          │
                         │   (Nginx/ALB)       │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
            ┌───────▼───────┐       │       ┌───────▼───────┐
            │  消息网关      │       │       │  Web UI       │
            │  (Layer 3)    │       │       │  (Layer 3)    │
            └───────┬───────┘       │       └───────┬───────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    │
                         ┌──────────▼──────────┐
                         │   API 网关          │
                         │   (Layer 2)         │
                         │   认证、限流、路由  │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │   核心服务          │
                         │   (Layer 1)         │
                         │   Agent、Skill、编排│
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
            ┌───────▼───────┐ ┌─────▼─────┐ ┌───────▼───────┐
            │  数据库       │ │  LLM      │ │  向量存储     │
            │  PostgreSQL   │ │  API      │ │  Milvus      │
            │  MongoDB      │ │           │ │              │
            └───────────────┘ └───────────┘ └───────────────┘
                    │               │               │
                         ┌──────────▼──────────┐
                         │   基础设施层        │
                         │   (Layer 0)         │
                         └─────────────────────┘
```

##### 部署拓扑

| 环境 | 架构 | 说明 |
|------|------|------|
| **开发环境** | 单机 Docker Compose | 本地开发、快速迭代 |
| **测试环境** | 单机 Kubernetes（Minikube） | 功能测试、集成测试 |
| **预发环境** | 多节点 Kubernetes（类生产） | 性能测试、安全测试 |
| **生产环境** | 多节点高可用 Kubernetes | 正式服务、高可用 |

---

#### 环境管理

##### 环境分类

| 环境类型 | 用途 | 数据 | 隔离性 | 访问权限 |
|----------|------|------|--------|----------|
| **开发** | 本地开发 | Mock/内存 | 开发机 | 开发者 |
| **测试** | 功能测试 | 测试数据 | 命名空间隔离 | 开发者、测试 |
| **预发** | 类生产测试 | 脱敏数据 | 环境隔离 | 开发者、测试、运维 |
| **生产** | 正式服务 | 生产数据 | 完全隔离 | 运维 |

##### 环境配置

**配置优先级**（从高到低）：

1. 环境变量
2. 密钥管理服务（Vault / Kubernetes Secrets）
3. 配置文件
4. 默认值

**配置文件结构**：

```
config/
├── base/                    # 基础配置
│   ├── database.yaml
│   ├── llm.yaml
│   └── vector.yaml
│
├── environments/           # 环境配置
│   ├── dev.yaml           # 开发环境
│   ├── test.yaml          # 测试环境
│   ├── staging.yaml       # 预发环境
│   └── prod.yaml          # 生产环境
│
└── secrets/                # 敏感配置（不提交）
    ├── database.yaml
    ├── llm.yaml
    └── vault.yaml
```

##### 环境变量规范

**命名规范**：

```bash
### 格式：<SERVICE>_<COMPONENT>_<KEY>

### 数据库
DATABASE_POSTGRES_HOST=localhost
DATABASE_POSTGRES_PORT=5432
DATABASE_POSTGRES_USER=postgres
DATABASE_POSTGRES_PASSWORD=secret

### LLM
LLM_OPENAI_API_KEY=sk-xxx
LLM_OPENAI_MODEL=gpt-4

### 向量存储
VECTOR_MILVUS_HOST=localhost
VECTOR_MILVUS_PORT=19530
```

**敏感信息管理**：

| 类型 | 存储位置 | 示例 |
|------|----------|------|
| 数据库密码 | Vault / K8s Secrets | `DATABASE_POSTGRES_PASSWORD` |
| API Key | Vault / K8s Secrets | `LLM_OPENAI_API_KEY` |
| 证书 | Vault / K8s Secrets | TLS 证书 |
| 配置文件 | Git（加密） | `config/secrets/*.enc.yaml` |

---

#### 部署顺序

##### 层级依赖关系

```
aiPlat-infra (Layer 0)    ← 最底层，最先部署
       ↓
aiPlat-core (Layer 1)    ← 依赖 infra
       ↓
aiPlat-platform (Layer 2) ← 依赖 core
       ↓
aiPlat-app (Layer 3)     ← 最上层，最后部署
```

##### 部署流程

```
┌─────────────────────────────────────────────────────────┐
│ Step 1: 部署基础设施（Layer 0）                          │
├─────────────────────────────────────────────────────────┤
│ - PostgreSQL / MySQL / MongoDB                          │
│ - Redis / RabbitMQ / Kafka                              │
│ - Milvus / ChromaDB                                     │
│ - MinIO / S3                                            │
│ - 日志、监控、追踪基础设施                              │
└────────────────────────┬────────────────────────────────┘
                         │ 等待基础设施就绪
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 2: 部署核心服务（Layer 1）                         │
├─────────────────────────────────────────────────────────┤
│ - 配置服务依赖的数据库、向量存储                       │
│ - 部署 core 服务                                        │
│ - 健康检查                                              │
└────────────────────────┬────────────────────────────────┘
                         │ 等待核心服务就绪
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 3: 部署平台服务（Layer 2）                         │
├─────────────────────────────────────────────────────────┤
│ - 配置平台服务依赖的 core 服务                         │
│ - 部署 platform 服务                                    │
│ - 配置认证、多租户、计费                               │
│ - 健康检查                                              │
└────────────────────────┬────────────────────────────────┘
                         │ 等待平台服务就绪

…

_(节选；全文见权威源)_


**节选自** [`docs/architecture/plans/disaster-recovery-plan.md`](../architecture/plans/disaster-recovery-plan.md)：

### aiPlat Disaster Recovery Plan（初稿）

> 框架三 macro.11 灾难恢复 2.5→3.0 baseline。本文件证明 aiPlat 具备基本的灾难恢复规划，而非"完全没有"。

last_synced: 2026-07-07
status: draft
owner: infra/ops

---

#### 1. 恢复策略（RPO/RTO）

| 组件 | RPO | RTO | 策略 | 当前实现 |
|------|:--:|:--:|------|---------|
| **执行状态 (PipelineState)** | <5min | <1min | ExecutionSnapshot save/load + checkpoint 回滚 | `pipeline_engine._snapshot` + `_load_checkpoints_from_disk` |
| **知识库 (Wiki/语义记忆)** | <1hour | <5min | SQLite WAL + 文件级备份 | `semantic.py` SQLite FTS5 + WAL |
| **Agent 配置 (AGENT.md/SKILL.md)** | <24h | 手动 | Git 版本控制 + `hermes-profile-install.sh` | `~/.aiplat/agents/` + `profile_packager.py` |
| **API 密钥 (Credentials)** | 零丢失 | 自动 | AES-256 加密 at rest + CredentialPool 自动轮换 | `SecretsManager` + `credential_pool.py` |
| **系统配置 (Env/YAML)** | <24h | 手动 | `env.example` + distribution.yaml | `docs/framework/assessment-spec.yaml` |

#### 2. 备份策略

| 层级 | 机制 | 频率 |
|------|------|------|
| 执行快照 | `state["_checkpoints"]` + `save_execution_snapshot()` | 每个阶段 |
| 本体图快照 | `GraphIndex.snapshot(label)` → SQLite `graph_snapshots` | 每次本体变更 |
| 数据库 | SQLite WAL 自动崩溃恢复 | 实时 |
| 配置 | Git 版本控制 (`.github/` + `docs/`) | 每次 commit |
| Profile | `profile_packager.py` → `distribution.yaml` + `.registry.yaml` | 每次变更 |

#### 3. 恢复流程（快速 checklist）

```
1. 确认故障范围: curl /api/core/health  → 检查各层状态
2. 恢复配置: hermes-profile-install.sh <distribution.yaml>
3. 恢复知识: 已有 SQLite WAL → 自动
4. 恢复运行: start.sh 重启服务
5. 验证: curl /api/core/diagnostics/summary
```

#### 4. 现有韧性基础设施

- ✅ 流水线自愈（5 策略: rotate_credential/compress/backoff/skip/escalate）
- ✅ 自动回滚（learning autorollback + canary auto-rollback）
- ✅ 熔断器（WikiCircuitBreaker + LLMCircuitBreaker）
- ✅ 凭证池（CredentialPool 多 key 轮换）
- ✅ 崩溃恢复（checkpoint + snapshot + crash restore）
- ❌ 多区域部署（K3s 单节点）
- ❌ 异地备份（无远程存储）
- ❌ 自动化恢复演练（Chaos Mesh 未部署）

#### 5. 差距与升级路径

| 当前基线 (3.0) | 下一阶段 (4.0) | 终极目标 (5.0) |
|------|------|------|
| 单机 SQLite WAL | 远程异地备份（S3/rclone） | 跨区域副本 |
| 手动恢复 checklist | 自动化恢复脚本 | Chaos 工程验证 |
| 单节点 K3s | 多节点 HPA | 多区域 K8s |

**当前 RTO/RPO 可接受单开发者规模。**


#### 3.3.2 性能与扩展性

**尽调问题**：性能预算、P95/容量目标、水平扩展与压测入口是什么？

基线数字仅引用 `slo.md`「Performance Baselines」；无独立压测报告时以脚本与门禁为证据。

**权威源**： [`docs/standards/规范-性能.md`](../standards/规范-性能.md) · [`docs/architecture/slo.md`](../architecture/slo.md) · `scripts/benchmark_all.sh` · `scripts/stress-test.sh`

**节选自** [`docs/standards/规范-性能.md`](../standards/规范-性能.md)：

### 规范-性能


#### 1. 架构守卫时间预算（已有）

| 检查 | 预算 |
|------|------|
| `architecture_guard.sh` 全量 | ≤ 120s（并行化 4 个独立脚本） |
| pre-commit `--quick` | ≤ 30s |

#### 2. 运行时性能红线

| 场景 | 要求 |
|------|------|
| 热路径（syscall/上下文装配） | 禁止阻塞式 LLM/IO；异步优先 |
| 工具输出 | >2000 字走占位符 + 后台摘要（工具输出预算帽） |
| 大文件 | >800KB 跳过 AST 解析（CodeGraph `read_text` max_bytes） |
| 缓存 | 频繁读取结果必须缓存（CodeGraph LRU、dashboard 30s TTL） |

#### 3. 禁止

- 在 HTTP 请求路径同步加载重型模型（embedding/reranker 走适配器懒加载）
- 无界循环/递归（检索、图遍历必须有深度/条数上限）
- 每请求重复构建重型对象（应复用单例/DI）

#### 4. 验证

```bash
bash scripts/architecture_guard.sh  # 超时约束 §0.5
```


**节选自** [`docs/architecture/slo.md`](../architecture/slo.md)：

### aiPlat Service Level Objectives

> **Status**: Draft | **Version**: 1.0 | **Owner**: aiPlat Architecture Team

#### Service Tier Definitions

| Tier | Services | Criticality | Target Availability |
|:---|:---|:--:|:--:|
| **Tier 1** | aiPlat-core (API), aiPlat-management (gateway) | Critical — platform unusable without | 99.9% |
| **Tier 2** | aiPlat-infra (LLM/model management) | High — degradation but not full outage | 99.5% |
| **Tier 3** | aiPlat-platform (builder/workflow) | Medium — batch operations, not real-time | 99.0% |

#### SLO Matrix

##### Tier 1: Core + Management (Critical)

| SLI | Target | Measurement Window |
|:---|:--:|:--:|
| **Availability** | ≥ 99.9% | 30 days |
| **Latency (P95)** | ≤ 500ms for agent execute endpoint | 30 days |
| **Error Rate** | ≤ 0.1% of all requests | 30 days |
| **LLM Response Time** | ≤ 30s for non-streaming | 30 days |
| **Pipeline Start Latency** | ≤ 5s from request to execution | 30 days |

##### Tier 2: Infra (High)

| SLI | Target | Measurement Window |
|:---|:--:|:--:|
| **Availability** | ≥ 99.5% | 30 days |
| **Model Health Check** | ≤ 10s response | 5 minutes |
| **Model Discovery Latency** | ≤ 1s to list models | 5 minutes |

##### Tier 3: Platform (Medium)

| SLI | Target | Measurement Window |
|:---|:--:|:--:|
| **Availability** | ≥ 99.0% | 30 days |
| **Builder Session Commit** | ≤ 3s | 30 days |

#### Error Budget

| Tier | Availability | Allowed Downtime (monthly) | Error Budget |
|:---|:--:|:--|:--:|
| Tier 1 | 99.9% | 43.2 minutes | 0.1% |
| Tier 2 | 99.5% | 3.6 hours | 0.5% |
| Tier 3 | 99.0% | 7.2 hours | 1.0% |

#### Alerting Thresholds

| Alert | Condition | Severity | Action |
|:---|:---|:--|:---|
| Tier 1 availability | Error rate > 1% (5 min) | Critical | PagerDuty |
| Tier 1 latency | P95 > 2s (5 min) | Warning | Slack |
| Tier 1 error rate | 50% budget consumed | Warning | Slack + Jira ticket |
| Tier 1 error rate | 90% budget consumed | Critical | PagerDuty |
| Tier 2 availability | Error rate > 5% (5 min) | Warning | Slack |
| Pipeline timeout | > 300s (1 occurrence) | Warning | Slack |

#### Measurement

All SLIs are measured via Prometheus metrics:

| SLI | Prometheus Metric |
|:---|:---|
| Availability | `http_requests_total{status_code!~"5.."}` / `http_requests_total` |
| Latency | `histogram_quantile(0.95, http_request_duration_seconds_bucket)` |
| Error Rate | `http_requests_total{status_code=~"5.."}` / `http_requests_total` |
| LLM Time | `llm_request_duration_seconds` |
| Pipeline Latency | `pipeline_start_latency_seconds` |

#### Review Cadence

| Activity | Frequency | Owner |
|:---|:---|:---|
| SLO review | Monthly | Architecture Team |
| Error budget review | Monthly | Platform Engineering |
| Alert threshold tuning | Quarterly | SRE |

#### Performance Baselines (Measured)

> Numbers collected from aiPlat v0.0.1 running on macOS M1 (local, no GPU). Production numbers will vary.

| Metric | Local (M1) | Target (Production) | Status |
|:---|:---:|:---|:--:|
| Agent execute P50 | ~2s | ≤ 200ms | ⚠️ local LLM bottleneck |
| Agent execute P95 | ~8s | ≤ 2s | ⚠️ local LLM bottleneck |
| Health check latency | <10ms | ≤ 50ms | ✅ |
| Model list latency | <100ms | ≤ 1s | ✅ |
| Pipeline start latency | ~3s | ≤ 5s | ✅ |
| Concurrent health checks | 50 req/s | 500 req/s | ⚠️ not stress tested |
| Wiki search latency | ~500ms | ≤ 1s | ✅ |
| Agent step latency (T1 model) | ~1s | ≤ 500ms | ⚠️ local|

**Stress test**: `bash scripts/stress-test.sh localhost 50 500`
**Continuous tracking**: Prometheus metrics → Grafana dashboard

#### K8s Readiness

Production deployment requires all liveness/readiness probes to pass:

```yaml
### Core service (Tier 1)
livenessProbe:
  httpGet: {path: /api/core/health, port: 8002}
  initialDelaySeconds: 30
  periodSeconds: 15
readinessProbe:
  httpGet: {path: /api/core/health, port: 8002}
  initialDelaySeconds: 15
  periodSeconds: 10
```

**Readiness gate checklist**:
- [ ] Core health endpoint returns 200
- [ ] Infra model list endpoint returns models  
- [ ] Management health/all returns 4-layer healthy
- [ ] Database WAL mode enabled (pool.db)
- [ ] Gossip protocol peers reachable (if multi-AZ)


#### 3.3.3 可观测性架构

**尽调问题**：日志 / 指标 / 追踪如何采集、关联与告警？

与安全卷可观测切片交叉；身份三元组规范见 trace/run/request id 标准。

**权威源**： [`docs/architecture/plans/observability-eval-repair-architecture.md`](../architecture/plans/observability-eval-repair-architecture.md) · [`docs/standards/规范-core-run_id-trace_id-request_id.md`](../standards/规范-core-run_id-trace_id-request_id.md)

**节选自** [`docs/architecture/plans/observability-eval-repair-architecture.md`](../architecture/plans/observability-eval-repair-architecture.md)：

### 评估 / 诊断 / 修复体系架构（As-Is 存档）

> 本文档存档 aiPlat "评估—诊断—告警—修复" 全链路的当前真实架构，含代码交叉验证证据（file:line）。
> 遵循根 `CLAUDE.md` §规则5：所有事实性声明附带 grep/file:line 证据。

last_synced: 2026-07-07
status: as-is
owner: harness/observability + evaluation
---

#### 0. 一句话总览

系统的"评估/诊断/修复"分**两个层面**，此前常被混淆：

- **层面一 — 系统成熟度评估框架（周期性/人工判定）**：评"系统多成熟/多好/能否持续"。三套框架（8轴自主性 / 工程落地58项 / 三层企业110项）+ 统一验证引擎 `compute_assessment.py`。见 §1.5。
- **层面二 — 运行时评估/诊断/告警/修复（连续/自动）**：评"跑起来好不好"。三个运行时评估器 + 诊断中心32维 + 五画面 + 八修复能力。见 §1–§5。

两层过去彼此独立、存在重复与断裂；本轮（提交 `a8371ce`→`af52ed5`）完成收敛、接线与"评估真实化"，形成 "评估→诊断→告警→建议→人工审批→修复" 的闭环，且**自主写入刻意默认关闭**。

---

#### 1. 运行时评估器 / 诊断 / 告警（层面二，评估对象各不相同）

> 注：本节的"三评估器"是**运行时代码级评估器**，**不是**用户口径的"三个评估架构"——后者指 §1.5 的成熟度框架。

| 体系 | 评估对象 | 位置 | 触发 |
|------|---------|------|------|
| A. 三运行时评估器 | 单次输出 / 生成内容 / 代码 diff | 见 §1.1 | 旁路/pipeline/anomaly |
| B. 诊断中心（32 维） | 系统级：代码/架构/知识/安全/runtime | `core/api/routers/diagnostics.py` | 后台每 300s（`server.py:1352`） |
| C. 管理端告警 | 四层聚合指标阈值 | `aiPlat-management/management/api/alerting.py` | 每 60s（`server.py:174`） |

##### 1.1 三评估器（A）
| 评估器 | 位置 | 定位 |
|------|------|------|
| 离线 eval | `core/harness/evaluation/` (`eval_runner.py`, `eval_metrics.py` 6维, `workbench.py` 阈值门, `compare.py` 纯代码回归判定) | 运行输出质量 |
| tri_agent | `core/harness/execution/langgraph/graphs/tri_agent.py` | 循环内 Planner→Generator→Evaluator |
| autoreview | `core/engine/skills/autoreview/` | diff-only 代码审查（温度分层/硬投票/MoA） |

**收敛（本轮）**：三者统一到 `workbench.validate_report` 的 `{pass, score, issues}` schema
（`review_report.py:to_evaluation_report`、`tri_agent.py:_to_evaluation_report`；`a8371ce`）。

##### 1.5 系统成熟度评估框架（层面一 — 用户口径的"三个评估架构"）

三套框架 + 统一验证引擎，源在 `docs/framework/`：

| 框架 | 问题 | 规模 | 计算综合(唯一) |
|------|------|------|------|
| 框架一 8轴自主性成熟度 + R轴 | 能做什么/多成熟/多抗造 | 34 项 | **L4 (3.91)** |
| 框架二 工程落地评估 | 能不能持续 | 59 项二进制 | **86.4%** |
| 框架三 三层企业评估 | 有多好 | 109 项 | 宏观3.42/微观3.94/架构3.64 |

**统一验证引擎** `scripts/compute_assessment.py`（源: `docs/framework/assessment-spec.yaml` 202项单一事实源 → `assessment-scores.json`）：

| 能力 | 命令 | 作用 |
|------|------|------|
| 验证+聚合 | `compute_assessment.py` | 跑证据命令验证 declared 值 + 确定性公式算综合分（消除 4.15/4.35/5.00 三头矛盾）；43 项可验证全 pass，109 判断项诚实标 manual |
| 漂移检测 | `--drift-only` | declared 有声明但证据失败 → 报漂移；层分自洽检查（曾抓到权重110% + 6.1 假漂移） |
| 文档回填 | `--render` | 幂等回填三框架文档 `<!-- AUTO-SCORE -->` 块，杜绝再漂移 |
| 能vs做过桥接 | `--bridge` | `runtime_ref` 项比对声明能力 vs 运行时遥测（A1.2 active=66 / F2 active=2 / A1.1 requires_live） |
| 框架发现→修复 | `--goals` | 缺口/漂移/工程no项 → 修复 Goal 提案（10项，`auto_executable=False`，接 §5 修复中心闭环） |

**诚实底线**：L 级/分数仍是**人工判定**（`declared_*`），引擎不推导 L 级，只做验证+聚合+漂移；无法验证的判断项诚实标 `source: manual, verified: null`。

---

#### 2. 五个管理画面 → 后端映射

| 画面 | 前端 | 关键 API |
|------|------|---------|
| 诊断程序 | `pages/Diagnostics/Diagnostics.tsx` | `POST /api/core/diagnostics/run-all`、`/guard/run`、`/latest` |
| 系统概览 | `pages/SystemOverview/SystemOverview.tsx` | `GET /api/core/overview`（四层聚合，`overview.py:230`） |
| 修复中心 | `pages/Diagnostics/RepairCenter.tsx` | `/repairs-latest` + **`/repairs/history`**（本轮新增） + **`/goals`**（本轮新增） |
| Agent评估 | `pages/Diagnostics/EvalDashboard.tsx` | `GET /api/core/evaluation/overview`（含 **`production_success`**，本轮新增） |
| 告警中心 | `pages/Alerts/Alerts.tsx` | `GET /api/alerting/alerts`（本轮合并 core 告警） |

---

#### 3. 本轮修复的问题（原分析→现状）

##### 3.1 重复/重叠 → 已收敛
| 问题 | 修复 | 证据 |
|------|------|------|
| 告警双轨断裂：管理端只算层指标，core 的熵/漂移/危机/文档告警不进告警中心 | 新增统一聚合 + 管理端合并 | `diagnostics.py:1685 aggregate_all_alerts`、`1767 get_all_alerts`；`server.py:174` 合并 `core:`/`mgmt:` |
| 评估序列化重复（router 手工 50 行） | 抽取共享序列化 | `eval_runner.py:122 serialize_eval_result`（router + loop 共用） |
| 三评估器 schema 各异 | 统一 EvaluationReport | `a8371ce`（见 §1.1） |

##### 3.2 真实性缺口 → 已补
| 缺口 | 修复 | 证据 |
|------|------|------|
| Agent 真实运行质量非自动评估（Agent评估页常空） | 每次运行 fire-and-forget 6维自动打分 | `base.py:223 _try_auto_score_run`；`eval_runner.py:184 persist_runtime_eval`（保留上限） |
| 无生产真实任务成功率 | 从 auto-runtime 结果连续汇总 | `evaluation.py:160 production_success`（仅统计 `eval_set_id=="auto-runtime"`） |

##### 3.3 自动修复 → 已可见 + 已闭环
| 缺口 | 修复 | 证据 |
|------|------|------|
| 修复中心 ≠ 真实修复全景 | 汇入自愈/AutoLearner/autoreview 历史 | `diagnostics.py:1059 aggregate_repair_history` |
| 诊断发现不驱动修复 | 诊断→建议→人工审批→执行闭环 | `diagnostics.py:1145 list_repair_goals`、`1164 execute_repair_goal`；`goal_executor.py:145 execute_goal` |

---

#### 4. 自动修复能力全景（8 条）

| # | 能力 | 自动 | 已接线 | 证据 |
|---|------|:---:|:---:|------|
| 1 | 流水线自愈（5 策略） | ✅4/5 | ✅ | `pipeline_engine.py:4484-4581` |
| 2 | GoalExecutor 自主循环 | 定义 | ❌ 未启用（安全） | `goal_executor.py:63 enabled=False` |
| 3 | autoreview 自动修 P2 | ⚠️ | ✅ | `autoreview/auto_fixer.py` |
| 4 | 学习/canary 回滚 | ✅ | ✅ | `learning/autorollback.py`、`deployment/canary.py` |
| 5 | AutoLearner 草稿+确认 | ✅高置信 | ✅ | `learning/__init__.py:372` |
| 6 | ToolBootstrap | ⚠️只读 | ✅ | `optimization/tool_bootstrap.py` |
| 7 | JSON/消息修复 | ✅ | ✅ | `postprocess.py:45`、`pipeline_engine.py:972` |
| 8 | on-error 反思 | ✅ | ✅ | `hooks/on_error_reflector.py` |

---

#### 5. 诊断→修复闭环安全模型（P1, `8f0e22b`）

闭环补全了 "诊断→建议→人工审批→执行"，但**刻意不开启自主后台执行**：

| 门禁 | 机制

…

_(节选；全文见权威源)_


**节选自** [`docs/standards/规范-core-run_id-trace_id-request_id.md`](../standards/规范-core-run_id-trace_id-request_id.md)：

#### 1. 三个 ID 的分工（必须分离）

| 名称 | 权威生成方 | 格式建议 | 目的 |
|---|---|---|---|
| request_id | platform | `req_<ulid>` | **幂等 + 审计关联**（一次“请求意图”） |
| run_id | core | `run_<ulid>` | **一次执行实例**（有生命周期/事件流/审批） |
| trace_id | core | `trace_<ulid>` 或 uuid | **观测链路**（span/syscalls/links） |

核心原则：
- **request_id ≠ run_id**：重试/转发/回放都围绕 request_id 做幂等；
- **run_id ≠ trace_id**：同一个 run 可能有多段 trace（例如内部重试/子流程），但对外仍是一条 run 记录。

##### 1.1 消歧记录（P0-C2，2026-08-16）

| 规范原文 | 代码事实 | 消歧 |
|---|---|---|
| run_id 格式 `run_<ulid>` | pipeline run_id 实际为 `run-<uuid12>`（`core/api/core_facade.py:1868`） | 格式为**建议值**，以代码实现为准（前缀 `run-` + 唯一 ID）；`run_<ulid>` 保留为推荐目标 |
| 未提及 job 调度 | `core/management/job_scheduler.py:179` 使用 `jobrun-<uuid12>` 独立命名空间 | 补充：**job 调度 run_id 与 pipeline run_id 命名空间分离**（`jobrun-` 前缀），不可混用 |

---

#### 2. 幂等：request_id → run_id 映射（推荐，未实现）

企业场景中（尤其 app→platform→core），建议由 core 提供一条幂等映射表：

- 表：`request_dedup(tenant_id, request_id, run_id, created_at, status)`
- 规则：
  1) platform 转发给 core 时必须带 `X-AIPLAT-REQUEST-ID`
  2) core 收到请求先查 `(tenant_id, request_id)`：
     - 若存在：直接返回已有 run_id（以及当前 run 状态）
     - 若不存在：生成新的 `run_<ulid>`，写入映射表，再开始执行

> **状态标注（P0-C2 更新，2026-08-19）**：`request_dedup` 表**已实现**（`core/services/execution_store_schema.py` 建表 + runs_mixin 幂等映射）。本节为当前实现描述。

这样可以保证：
- 上游超时重试不会创建重复 run
- 审计、审批、回放都能以 request_id 聚合

---

#### 3. 贯穿字段（落库/事件/审计）

core 在以下记录中都应写入三者（至少 run_id + trace_id + request_id）：
- `run_events`（run_id + trace_id + tenant_id）
- `syscall_events`（run_id + trace_id + tenant_id + target_type/target_id）
- `agent_executions/skill_executions/tool_executions`（run_id + trace_id + tenant_id）
- `approval_requests`（run_id + request_id + tenant_id）
- `audit_logs`（action 的 request_id + run_id + actor）

management 展示层建议以：
1) run_id 作为主对象；
2) trace_id 作为“钻取链接”；
3) request_id 作为“跨系统关联键”（platform/app 的日志也用它聚合）。


---

#### 4. 自动触发 run 的产生源（P2-A6/A7，2026-08-16 补充）

`core/harness/execution/event_loop.py` 的 loop scheduler 是自动 run 的产生源之一，新增两种模式：

| 模式 | 触发方式 | run 语义 |
|------|---------|---------|
| `mode=script`（P2-A7） | cron 触发，`params.mode="script"` | **无 run_id**——直接执行 shell/python 脚本（零 LLM），结果经 `result_channel` 投递；不产生 pipeline run 记录 |
| `mode=goal`（P2-A6） | goal 触发，每轮 `_judge_goal_condition` 评估 | 未达成时 `_start_pipeline_from_scene` 产生 pipeline run（`run-<uuid12>`），`iterations_left` 预算内续跑；达成或预算耗尽停止 |

**契约要点**：
- script 模式**不落 run 记录**（无 LLM、无 pipeline 状态机）——观测通过 scheduler 日志（`script trigger ...: OK`）完成
- goal 模式的每次续跑都是**独立 run**（run_id 前缀 `run-`），通过 trigger_id + `iterations_left` 关联

…

_(节选；全文见权威源)_


#### 3.3.4 数据架构

**尽调问题**：知识/业务数据存哪里、如何隔离与备份？

`knowledge-base-architecture.md` 已合并至 `knowledge-system.md`；备份策略交叉 §3.3.1 灾备计划。

**权威源**： [`docs/knowledge-system.md`](../knowledge-system.md) · [`docs/architecture/knowledge-base-architecture.md`](../architecture/knowledge-base-architecture.md)

**节选自** [`docs/knowledge-system.md`](../knowledge-system.md)：

### aiPlat 知识系统 — 完整指南

> 最后更新: 2026-08-11 · 原理优先，细节后置 · API/SQL/操作见附录

---

#### 一、知识系统要解决什么问题

企业的知识散布在 PDF、Word、HTML、视频和数据库中。传统 RAG 面临三个核心挑战：

**1. 如何将异构资料转化为可检索的结构化知识？**
解决方案：一条 5 阶段管线。资料摄入→本体提取→向量索引→Wiki 合成→多路检索。
纯文本检索只能匹配关键词，无法理解「这篇 PDF 第 3 页的表格」和「那篇 Word 的第三章」讨论的是同一个概念。

**2. 如何让 RAG 检索到最相关的知识，而不是被无关内容淹没？**
解决方案：三大存储体系各司其职。向量 KB 存原始片段（搜原材料），GraphIndex 存实体/关系（搜结构化知识），LLM Wiki 存百科页面（搜人类可读知识）。检索时三路并行，路由到正确域过滤噪音。

**3. 如何发现知识缺口并自动补充？**
解决方案：质量闭环。HallucinationTracker 检测不忠实话→CandidatePool 积累候选缺口→ActiveSynthesis 自动生成补充页面→回写 Wiki。N≥3 次同一缺口才触发，避免误报。

##### 三大存储体系速览

```
┌─────────────────────────────────────────────────────────────────┐
│                         三大存储，各司其职                         │
├───────────────┬──────────────────┬──────────────────────────────┤
│ 向量 KB       │  GraphIndex      │  LLM Wiki                    │
│ 原始文档片段   │  知识结构图       │  人类可读百科页面              │
│ (SQLite)      │  (SQLite)        │  (Markdown 文件)              │
├───────────────┼──────────────────┼──────────────────────────────┤
│ 存什么        │ 存什么            │ 存什么                        │
│ 解析后的文本   │ 实体节点+关系边    │ 实体页+合成页+矛盾页           │
│ 片段+向量      │ +超边            │ +知识原子                     │
├───────────────┼──────────────────┼──────────────────────────────┤
│ 谁写          │ 谁写              │ 谁写                          │
│ 文档入库管线    │ 本体引擎 Step 10  │ KnowledgeSynthesizer         │
│ (不需要本体引擎) │ (提取实体+关系)    │ (从 GraphIndex 合成)          │
├───────────────┼──────────────────┼──────────────────────────────┤
│ 谁读          │ 谁读              │ 谁读                          │
│ SqliteEmbedding│ BFS 图遍历       │ WikiPageRetriever             │
│ Retriever     │                  │                              │
├───────────────┼──────────────────┼──────────────────────────────┤
│ 核心原则       │                  │                              │
│ 本体引擎不修   │                  │                              │
│ 改向量 KB     │                  │                              │
└───────────────┴──────────────────┴──────────────────────────────┘
```

> 关于 TripleStore（将 5 个图连接为统一知识网络）请参见 §四·本体层。

---

#### 二、核心架构：三大存储 + 一条管线

```
用户查询
  │
  ├── [1] 资料摄入: DocumentParser→StructuredChunk→向量KB（零LLM，秒级可用）
  │
  ├── [2] 本体提取: OntologyEngine→实体/关系→GraphIndex（LLM异步，后台运行）
  │
  ├── [3] Wiki 合成: KnowledgeSynthesizer→Wiki 页面（从GraphIndex生成可读百科）
  │
  ├── [4] 知识检索: DomainRouter→三路并行→CRAG回退→RRF融合→答案
  │       Wiki(语义) + KB向量 + FTS5(关键词)
  │
  └── [5] 质量闭环: HallucinationTracker→ActiveSynthesis→回写Wiki
          不忠实话→候选缺口→自动补知识
```

##### 各阶段职责

| 阶段 | 组件 | 输入 | 输出 | LLM？ |
|:---:|------|------|------|:---:|
| ① 摄入 | DocumentParser | PDF/Word/HTML/MD | StructuredChunk | 否 |
| ② 提取 | OntologyEngine | StructuredChunk + 域YAML | 实体/关系→GraphIndex | 部分（PropertyExtractor） |
| ③ 合成 | KnowledgeSynthesizer | GraphIndex 实体/关系 | Wiki 页面 | ActiveSynthesis可选 |
| ④ 检索 | DomainRouter+CRAG+RRF | 用户查询 | 带来源的答案 | HyDE level 3 |
| ⑤ 闭环 | HallucinationTracker+ActiveSynthesis | ④的输出+用户信号 | 知识缺口→自动补充 | ActiveSynthesis |

##### 异步最终一致性

引擎采用异步最终一致性模型：
- ClassMapper（零 LLM）打粗粒度标签后，**先行落地基础向量索引**，保证检索立即可用
- PropertyExtractor（LLM）+ GraphBuild 作为**增强管线异步运行**
- 管线崩溃/超时时，**基础索引仍可服务**，RAG 不会完全不可用
- 增强完成后覆盖更新向量 + 更新 Wiki 页面

---

#### 三、资料层：如何将文档变成可检索的知识

##### 3.1 核心原则

**资料上传后立即创建基础索引（零 LLM，秒级可用）**。本体增强（LLM 提取实体/关系）在后台异步运行——二者独立，互不阻塞。

##### 3.2 摄入路径

| 方式 | 操作 | 适用场景 |
|------|------|------|
| 页面上传 | 知识 → **知识库** / Vault 上传 | 少量文件 |
| API 上传 | `POST /api/core/wiki/ingest` | 外部系统对接 |
| URL 导入 | 知识中心 → 粘贴 URL | 在线文档 |

##### 3.3 支持格式

| 格式 | 解析器 | 说明 |
|------|--------|------|
| PDF | DocumentParser (MinerU / Tesseract) | 表格保留为 StructuredTable |
| DOCX/PPTX | DocumentParser | 保留标题层级 |
| HTML | DocumentParser (BeautifulSoup) | 保留结构 |
| Markdown | DocumentParser (内置) | 保留 heading 路径 |
| TXT | DocumentParser (内置) | 纯文本 |
| 图片 | DocumentParser (OCR) | 图像提取文本 |
| 视频 | DocumentParser (Whisper) | 转写+帧提取 |

外部数据源通过 DataSource 抽象层连接（SQL/API/CSV/Excel），不移动数据。

##### 3.4 数据存储

存入 `kb_elements` 表（文本片段 + 向量），`kb_elements_fts` 表（全文索引）。DomainRouter 根据内容自动分类到对应域。

> 完整表结构和接入方式参见[附录 B](#附录-b存储表结构)。

---

#### 四、本体层：如何从文本中提取结构化知识

##### 4.1 本体与三大存储的关系

本体层是五阶段管线中**承上启下的核心连接组织**。它从向量KB读取文档片段，提取实体/关系写入 GraphIndex，再经由 KnowledgeSynthesizer 生成 LLM Wiki 页面——最终这些 Wiki 页面成为 RAG 检索的主要数据源。

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  向量KB                  GraphIndex           LLM Wiki    │
│  原始文档片段  ──提取──→  实体+关系  ──合成──→  百科页面   │
│  (不用本体引擎)          (本体引擎 Step10)    (Step11)     │
│        │                      ▲                  │        │
│        │                      │                  │        │
│        └── 引擎读取文档 ──────┘                  │        │
│                                                  │        │
│        ┌─────────────────────────────────────────┘        │
│        ▼                                                  │
│  RAG 检索（三路并行）                                      │
│  Wiki语义 + KB向量 + FTS5关键词                            │
│  ← DomainRouter 域路由 + CRAG回退 →                        │
└──────────────────────────────────────────────────────────┘
```

**四个核心关系**：

1. **向量KB→本体**：本体引擎从 `kb_elements` 表中读取文档片段，提取实体和关系写入 GraphIndex。向量KB 是「原材料仓库」，本体是「提炼后的知识模型」——二者独立运行，向量KB 不需要本体也能提供基础检索。
2. **本体→LLM Wiki**：KnowledgeSynthesizer 读取 GraphIndex 中的实体/关系，生成结构化 Wiki 页面。一个实体可对应多个页面：实体页（基本描述）、合成页（跨文档整合）、矛盾页（不一致检测）。
3. **本体→RAG 检索**：三重注入——DomainRouter 用域 YAML 定义的类标签路由查询到正确域、WikiPageRetriever 搜索本体引擎生成的 Wiki 页面、GraphIndex 遍历将实体关系作为检索关键词增强。
4. *

…

_(节选；全文见权威源)_


**节选自** [`docs/architecture/knowledge-base-architecture.md`](../architecture/knowledge-base-architecture.md)：

> 📦 **本文档已合并至** [docs/knowledge-system.md](../knowledge-system.md)
> 知识库架构内容（三大存储、表结构、RAG 检索链路）现统一归并到该文档中。



#### 3.3.5 安全架构嵌入视图（技术视角）

**尽调问题**：PolicyGate / Sandbox / 信任边界如何嵌进运行时？

完整威胁模型与治理叙事见分卷 05；此处只给技术嵌入视图。

**权威源**： [`docs/security/security-architecture.md`](../security/security-architecture.md)

**节选自** [`docs/security/security-architecture.md`](../security/security-architecture.md)：

### aiPlat 安全架构 — 纵深防御模型

> 基于零信任原则 (never trust, always verify) 的六层防御体系。

#### 防御层级

| 层 | 名称 | 机制 | 实现 |
|:--:|:---|:---|:---|
| **L1** | 网络边界 | API 网关, TLS, CORS | Management API Gateway (port 8000) |
| **L2** | 身份认证 | JWT Bearer Token | 单用户模式可选, 多租户强制 |
| **L3** | 权限控制 | RBAC + PBAC | PolicyGate (deny-by-default) + Permission Check |
| **L4** | 操作审批 | HITL Approval | ApprovalGate + 审批申请/批准/拒绝 |
| **L5** | 执行沙箱 | Isolated Subprocess | SandboxGate — 工具执行隔离 |
| **L6** | 审计追溯 | SHA-256 Chain | Audit Mixin — 回查每条操作 |

#### 零信任原则落地

| 原则 | aiPlat 实现 |
|:---|:---|
| 持续验证 | PolicyGate 每次 syscall 前检查权限 |
| 最小权限 | deny-by-default 策略, 必须显式授权 |
| 微分段 | Skill/Tool/Agent 权限独立, 互不继承 |
| 假定被破 | SandboxGate 隔离, 工具执行不在主进程 |
| 全程审计 | SHA-256 hash chain, 每次操作不可否认 |

#### 安全边界

```
Internet → Management Gateway (唯一入口)
              ↓ PolicyGate (RBAC 检查)
              ↓ API 路由
              ├── Core (Agent Engine + Pipeline)
              │     ↓ ApprovalGate (高危操作审批)
              │     ↓ SandboxGate (工具执行隔离)
              ├── Infra (Model Management + LLM)
              │     ↓ SecretsManager (AES-256-GCM 密钥)
              └── Platform (Knowledge Base + Builder)
                    ↓ Audit Log (SHA-256 chain)
```

#### GitHub Branch Protection Rules (Recommended)

```yaml
### Apply in GitHub → Settings → Branches → Add rule
branches: [main]
rules:
  - require_pull_request: true
    required_approvals: 1
    dismiss_stale_reviews: true
  - require_status_checks: true
    contexts: ["Lint & Type Check", "Test (pytest)", "L5 Depth Tests"]
  - require_conversation_resolution: true
  - require_code_owner_review: false  # no CODEOWNERS file
  - enforce_admins: true
```

#### 零信任验证清单

| # | 层级 | 验证方式 | 状态 |
|:--:|:---|:---|:--:|
| L1 | 网络边界 | `curl http://localhost:8000/health` — 只有 mgmt 端口暴露 | ✅ |
| L2 | 身份认证 | JWT 无效时返回 401 — `scripts/security-attack-sim.py` S1 验证 | ✅ |
| L3 | 权限控制 | PolicyGate deny-by-default — 未授权 tool 调用被拒绝 | ✅ |
| L4 | 操作审批 | ApprovalGate 高危操作需审批 — change_control.py 验证 | ✅ |
| L5 | 执行沙箱 | SandboxGate 隔离 — 工具执行不在主进程 | ✅ |
| L6 | 审计追溯 | SHA-256 chain 可验证 — `audit_mixin.py verify_integrity()` | ✅ |

#### FDE 部署验证报告

> 外部人员按 deploy-guide.md 从头部署并计时。

| 步骤 | 内容 | 耗时 | 状态 |
|:--:|------|:--:|:--:|
| 1 | git clone + pip install | ~3min | ✅ |
| 2 | 配置 API Key | ~1min | ✅ |
| 3 | `./start.sh` | ~2min | ✅ |
| 4 | `curl /health` 验证 | ~10s | ✅ |
| 5 | 运行第一个 Agent | ~1min | ✅ |
| 6 | `verify-l4-pyramid.sh` 全量验证 | ~10s | ✅ |
| 7 | `verify-deploy.sh` 部署验证 | ~30s | ✅ |
| **总计** | | **~8 分钟** | **从头部署到全量验证通过** |

##### FDE 差距

| 项 | 状态 | 说明 |
|:---|:--:|:---|
| 新手无障碍部署 | ✅ | 8分钟从零到验证 |
| 生产部署就绪 | ✅ | Helm + ArgoCD + 回滚 |
| 外部人验证 | 需要 | 邀请未接触过 aiPlat 的人做盲测 |
| 大规模部署 | 待验证 | 需要 K8s 集群 + 100 并发压力测试 |


#### 3.3.6 测试与验证策略

**尽调问题**：测试金字塔、CI/CD 与执行质量门禁如何构成验收闭环？

**权威源**： [`docs/manuals/testing.md`](../manuals/testing.md) · [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md) · `.github/workflows/` · `scripts/architecture_guard.sh`

**节选自** [`docs/manuals/testing.md`](../manuals/testing.md)：

### AI Platform 测试指南

> 系统级测试策略、分层测试方法、跨层测试规范

---

#### 📋 目录

- [测试策略](#测试策略)
- [分层测试原则](#分层测试原则)
- [测试类型](#测试类型)
- [测试环境](#测试环境)
- [跨层测试规范](#跨层测试规范)
- [测试覆盖率要求](#测试覆盖率要求)
- [CI/CD 集成](#cicd-集成)
- [各层测试指南](#各层测试指南)

---

#### 测试策略

##### 测试金字塔

AI Platform 采用测试金字塔策略，确保测试效率和可靠性：

```
        ┌─────────┐
        │   E2E   │  5-10%  端到端测试
        └─────────┘
      ┌─────────────┐
      │ Integration │  15-25%  集成测试
      └─────────────┘
    ┌───────────────────┐
    │    Unit Tests     │  70-80%  单元测试
    └───────────────────┘
```

**测试金字塔原则**：
- **单元测试**：数量最多，执行最快，测试独立单元
- **集成测试**：测试模块间的协作
- **E2E 测试**：验证完整用户场景

---

#### 分层测试原则

##### 各层测试职责

每个层级都有独立的测试职责，遵循单向依赖原则：

| 层级 | 测试职责 | 测试范围 |
|------|----------|----------|
| **Layer 0 (infra)** | 基础设施正确性 | 数据库连通性、LLM 连接、向量存储、消息队列 |
| **Layer 1 (core)** | 业务逻辑正确性 | Agent 执行、Skill 调用、编排流程、记忆系统 |
| **Layer 2 (platform)** | API 正确性 | REST/GraphQL 端点、认证授权、多租户隔离 |
| **Layer 3 (app)** | 用户体验正确性 | 消息网关、CLI 命令、Web UI 交互 |

##### 测试依赖规则

**允许的测试依赖**：
```
infra 测试 → 无依赖（独立测试基础设施）
core 测试 → 可以使用 infra 的 Mock/Stub
platform 测试 → 可以使用 core 的 Mock/Stub
app 测试 → 可以使用 platform 的 Mock/Stub
```

**测试隔离原则**：
- 单元测试：完全隔离，使用 Mock/Stub
- 集成测试：测试真实集成点，使用测试容器
- E2E 测试：测试真实系统，使用专用测试环境

---

#### 测试类型

##### 1. 单元测试

**定义**：测试独立单元的逻辑正确性

**原则**：
- 测试单个函数/方法/类
- 使用 Mock/Stub 隔离外部依赖
- 快速执行（< 100ms per test）
- 覆盖边界条件、错误处理

**示例**：
```python
### infra 层单元测试
def test_database_client_build_query():
    client = DatabaseClient(config)
    query, params = client._build_query("SELECT * FROM users WHERE id = :id", {"id": 1})
    assert "SELECT" in query
    assert params == (1,)

### core 层单元测试
def test_agent_executor_with_mock_llm():
    mock_llm = MockLLM(responses=["test response"])
    executor = AgentExecutor(llm=mock_llm)
    result = executor.execute("test input")
    assert result.content == "test response"
```

**覆盖率要求**：
- 核心业务逻辑：≥ 90%
- 基础设施代码：≥ 80%
- API 端点：≥ 70%

---

##### 2. 集成测试

**定义**：测试多个模块协作的正确性

**原则**：
- 测试真实集成点
- 使用测试容器（Testcontainers）管理外部服务
- 测试后清理资源
- 记录测试数据

**示例**：
```python
### infra 层集成测试
@pytest.fixture
async def postgres_container():
    container = PostgresContainer("postgres:15")
    container.start()
    yield container
    container.stop()

async def test_postgres_crud(postgres_container):
    client = PostgresClient(postgres_container.get_connection_url())
    await client.insert("users", {"name": "test"})
    users = await client.query("SELECT * FROM users")
    assert len(users) == 1

### core 层集成测试（使用真实数据库和 LLM Stub）
async def test_agent_with_real_database(test_db):
    agent = Agent(db=test_db, llm=StubLLM())
    result = await agent.execute("save user preference")
    assert result.success
```

**测试容器策略**：
- PostgreSQL/MySQL/MongoDB：使用官方测试容器
- Redis/RabbitMQ/Kafka：使用官方测试容器
- LLM API：使用 Mock 服务器
- 向量存储：使用 lightweight 容器（FAISS 内存模式）

---

##### 3. 端到端测试

**定义**：验证完整的用户场景

**原则**：
- 测试真实用户场景
- 使用专用测试环境
- 测试后清理数据
- 避免过度依赖 E2E

**示例**：
```python
### E2E 测试 - 完整对话流程
async def test_user_chat_flow(test_app):
    # 1. 用户登录
    response = await test_app.post("/auth/login", json={"username": "test", "password": "test"})
    assert response.status_code == 200
    
    # 2. 创建 Agent
    response = await test_app.post("/agents", json={"name": "test-agent", "model": "gpt-4"})
    assert response.status_code == 201
    agent_id = response.json()["id"]
    
    # 3. 发送消息
    response = await test_app.post(f"/agents/{agent_id}/chat", json={"message": "hello"})
    assert response.status_code == 200
    
    # 4. 验证响应
    assert "content" in response.json()
```

---

##### 4. 性能测试

**定义**：验证系统性能指标

**测试指标**：
| 指标 | 目标 | 工具 |
|------|------|------|
| 响应时间 | P95 < 500ms | locust、k6 |
| 吞吐量 | > 1000 QPS | locust、k6 |
| 并发数 | 支持 100 并发 | locust、k6 |
| LLM 调用延迟 | P95 < 3s | 自定义脚本 |

**示例**：
```python
### 性能测试 - API 吞吐量
def test_api_throughput(benchmark):
    result = benchmark(test_app.get, "/agents")
    assert result.stats.mean < 0.1  # 平均响应时间 < 100ms
```

---

##### 5. 安全测试

**定义**：验证系统安全性

**测试内容**：
- 认证授权测试（JWT 验证、权限控制）
- SQL 注入测试
- XSS 攻击测试
- CSRF 保护测试
- API 密钥保护测试
- 敏感数据脱敏测试

**示例**：
```python
### 安全测试 - SQL 注入
async def test_sql_injection_prevention(test_app):
    response = await test_app.post("/agents", json={
        "name": "'; DROP TABLE agents; --",
        "model": "gpt-4"
    })
    assert response.status_code != 500
    assert "error" in response.json()
```

---

#### 测试环境

##### 环境分类

| 环境 | 用途 | 数据 | 隔离性 |
|------|------|------|--------|
| **单元测试** | 开发机本地 | Mock/Stub | 完全隔离 |
| **集成测试** | 开发机本地 | 测试容器 | 进程隔离 |
| **CI 测试** | CI Runner | 测试容器 | 容器隔离 |
| **测试环境** | 独立服务器 | 测试数据 | 环境隔离 |
| **预发环境** | 类生产配置 | 脱敏数据 | 环境隔离 |
| **生产环境** | 正式服务 | 生产数据 | 完全隔离 |

##### 测试数据管理

**原则**：
- 单元测试：使用 Mock 数据，不依赖外部数据
- 集成测试：使用测试容器，测试后清理
- E2E 测试：使用专用测试数据库，测试后清理

**数据隔离策略**：
```python
### 每个测试使用独立数据库
@pytest.fixture
async def test_db():
    container = PostgresContainer("postgres:15")
    container.start()
    client = PostgresClient(container.get_connection_url())
    yield client
    container.stop()  # 测试后自动清理
```

---

#### 跨

…

_(节选；全文见权威源)_


**节选自** [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md)：

### 执行产物质量门禁矩阵（产物类型 → 规则）

> **真相源（代码）**：`aiPlat-core/core/management/execution_quality_review.py`  
> **配置审核**：Agent `workspace_agents.audit_agent_config`；Skill/Tool/MCP/Workflow 各自 `*/audit`  
> **能力登记**：[`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md)「执行后产物质量复核」等条目  
> **生成物**：平台横切治理；生成应用若走同一 `review_execution_output` / 资产 audit 则适用（管理端执行弹窗与 pipeline stage 已接线）。

本文回答三件事：

1. **编辑 / 执行壳是共通的**——不要给每个 Agent 复制 Modal。  
2. **假 A 按产物形状加规则**——PRD ≠ 架构 ≠ 代码。  
3. **Skill / Tool / MCP / Workflow** 要不要「像 Agent 一样再处理一遍」、**画面优化**是共通还是各改各的。

---

#### 1. 资产类型总表（Skill / Tool / MCP / Workflow / Agent）

| 资产 | 配置 AI 审核 | 执行后产物复核 | 还要不要「像 Agent 那样整轮重做」 |
|------|--------------|----------------|----------------------------------|
| **Agent** | ✅ `POST /workspace/agents/{id}/audit` | ✅ `review_execution_output(kind=agent)` | 否。配置侧已对齐「引擎 Skill 未在库」；产物侧按形状加规则 |
| **Skill** | ✅ `POST /workspace/skills/{id}/audit` + lint/apply-fix | ✅ 同一 `review_execution_output` + `review-output` API | **否重做壳**。新假 A → `_looks_*` + 规则 |
| **Tool** | ✅ `POST /tools/{name}/audit` | ✅ 已接线（偏 schema / 空输出 / logical_failure） | 一般够用；特殊 Tool 产物再加规则 |
| **MCP** | ✅ `POST /workspace/mcp/servers/{name}/audit` | ⚠️ 无对等「调用产物质量门」 | 审核已有；若要对 tools/call 结果建门再扩展 |
| **Workflow** | ✅ `POST /platform/workflows/{id}/audit` | ✅ `review_pipeline_stage`（按节点） | **否重做壳**。阶段产物走节点绑定的 Skill/Agent 规则 |

原则：

- **配置假 A**（未在库 / 未上架）→ 走各资产 `audit`，改共通门禁逻辑，不是按资产复制 UI。  
- **产物假 A**（PRD 软 AC、架构公有云等）→ 只扩 `execution_quality_review.py`，Workflow 阶段自动吃到同一套。

验证：

```bash
grep -n "audit_agent_config\|audit_tool_config\|review_execution_output\|review_pipeline_stage\|resolve_review_io_from_store" \
  aiPlat-core/core/api/routers/workspace_agents.py \
  aiPlat-core/core/api/routers/tools.py \
  aiPlat-core/core/management/execution_quality_review.py
```

**Stream 输入连续性**（防假 fail / 误判定稿）：

1. Agent/Skill seed + final upsert **必须**写入 `input`（Agent 经 `run_workspace_agent(input_payload=…)`）。  
2. 完成时 `metadata.quality_review` 由服务端写入；`GET /executions/{id}/status` 回传 `input` + `quality_review`。  
3. `POST …/review-output` 在 body.input 空时用 `execution_id` → `resolve_review_io_from_store` 回填。  
4. 输入仍空时：`review_input_missing`（warning）+ 按 OQ 形状 last-resort draft；**禁止**在无 input 时跑 `invented_nfr`（否则产物短语全变「编造」）。

---

#### 2. 画面：统一渲染（schema 驱动）vs 可选专属打磨

**答案：不必一个 Agent 一个画面。** 统一扩展点是 Skill 的 `output_schema`（+ 可选 `x-display-profile`）；UI 默认用通用结构化树渲染。

| 层 | 是否必做 | 说明 |
|----|:--------:|------|
| **执行壳 / 质量面板 / 审核** | ✅ 一次到位 | `Execute*Modal`、`ExecutionQualityReviewPanel`、`AssetAuditPanel` |
| **`GenericObjectOverview`** | ✅ **统一默认** | 任意对象/数组：按 `output_schema.properties` 排序/标签；无 schema 时按结构推断。**新 Skill 声明契约即可，零 UI 白名单** |
| **`PrdOverview` / `ArchitectureOverview`** | ⚪ 可选加分 | 仅当 schema `x-display-profile` / 产物 `document_type` 显式声明时启用 |
| **按 Agent 名复制 Modal** | 🚫 禁止 | 入口共通，结果走同一 `StructuredSkillOutput` |

| UI 块 | 共通？ | 说明 |
|-------|--------|------|
| `ExecutionQualityReviewPanel` | ✅ 共通壳 | Skill / Agent / Tool / 全屏流程复用 |
| `ExecuteResultPanel` | ✅ 共通壳 | 透传 `outputSchema` → `StructuredSkillOutput` |
| `AssetAuditPanel` | ✅ 共通 | Skill / MCP / **Agent** 共用；问题项优先，通过项（`*_binding_ok` / 引擎 Skill）可折叠 |
| `StructuredSkillOutput` | ✅ **统一路由器** | profile（schema/document_type）→ 专属 Overview；否则 `GenericObjectOverview(schema)` |
| `Edit*` / `Execute*` Modal | ⚠️ 文件分开 | 载荷/表单不同；**禁止**再按角色拆 Modal |

##### 2.1 渲染优先级

1. Skill 声明 `output_schema.x-display-profile: prd|architecture`（或产物 `document_type`）→ 专属 Overview  
2. **任意其它 JSON** → `GenericObjectOverview`（读 schema 排序/描述；无 schema 仍可读）  
3. Markdown `##` → `MarkdownCards`  
4. 纯文本 → `<pre>`

**扩展规则（统一方法）**：

```yaml
### SKILL.md
output_schema:
  x-display-profile: prd   # 可选：仅当需要专属布局（UI 元数据，不是 LLM 必填字段）
  type: object
  properties:
    title: { type: string, description: 标题 }
    # …字段顺序与 description 驱动管理端分区
```

**契约坑（强制）**：`x-display-profile` / `type` / `required` / `description` 是 schema 脚手架，**禁止**当作 LLM 顶层输出键。
Skill 执行器经 `_output_schema_payload_keys` 只取 `properties.*`（或过滤 meta 后的扁平字段）写入 JSON-override；
解析失败时回落 `{"text": …}`，**禁止**再 wrap 进 `x-display-profile`（否则会出现「步骤1 CoT 塞进 display-profile」的假产物，见 run-cadf97）。

新 Agent / Skill：**默认只改 SKILL.md 契约，不改前端。** 仅当通用树不够用时才加专属 Overview。后端假 A 规则仍按产物形状扩展 `execution_quality_review.py`，与 UI 解耦。

**改审核红灯 / 质量面板** → 改共通壳。  
**改「何为合格产物」** → 后端规则。  
**改「执行结果能不能读」** → `GenericObjectOverview` + `output_schema`；专属 Overview 只做观感加分。

---

#### 3. 共通壳（配置 + 执行）

| 能力 | 入口 | 说明 |
|------|------|------|
| Agent 编辑 / 绑定 / AI 审核 | `EditAgentModal` +

…

_(节选；全文见权威源)_


#### 3.3.7 技术风险与演进

**尽调问题**：技术债、依赖风险、版本兼容与架构演进路线？

债务清单以根 `CLAUDE.md` §16 与 ROADMAP 为准；商业卷只摘非财务路线。

**权威源**： [`AIPLAT_ROADMAP.md`](../../AIPLAT_ROADMAP.md) · [`docs/research/architecture-evolution-roadmap.md`](../research/architecture-evolution-roadmap.md) · [`CLAUDE.md`](../../CLAUDE.md)

**节选自** [`CLAUDE.md`](../../CLAUDE.md)（含「已知例外与永久债务」章节）：

### aiPlat 工作区级 AI 编程规约（Workspace Root）

此文件是 **工作区兜底规约**，用于在系统执行链路中自动推断到 workspace root 时仍然能注入/强制基本规则。

**能力全貌**：参见 [`AIPLAT_CAPABILITIES.md`](./AIPLAT_CAPABILITIES.md)（唯一真相源，见该文件当前计数）

**架构定位**：企业大脑 — 从"工具集合"到"自演进操作系统"的 8 层架构：

| 层 | 定位 | 操作系统类比 | 核心实现 |
|:--:|------|:--:|------|
| 1 | 本体语义底座 | 文件系统 — 定义数据如何组织和理解 | 8域YAML + GraphIndex + EntityResolver |
| 2 | 知识创造引擎 | 进程调度 — 动态生成和转化知识 | SECI Bus (POST_LOOP → atom → convergence) |
| 3 | 上下文注入总线 | 内存管理 — 为运行中的任务提供上下文 | ContextBus (10层注入, 4子系统覆盖) |
| 4 | 质量评分总线 | 安全机制 — 确保输出符合标准 | Quality Bus (4子系统统一评分 0-100) |
| 5 | FDE诊断与交付闭环 | Shell — 用户直接交互的界面 | 诊断→证据映射→覆盖率→改进→交付手册→跟踪→评分→对比→基准→目标分解→自主部署→外部发现 |
| 6 | 治理工程化 | 系统日志 — 记录和度量所有操作 | 8项治理能力 + 自审计 + 配置驱动 + 术语自播种 |
| 7 | 自演进操作系统 | 自动更新 — 自我修复和进化 | 四阶段全自动(观察/诊断/修复/演化) + 后台每小时调度 |
| 8 | 编码宪法 | 内核约束 — 所有操作必须遵守的基本法则 | karpathy_v1 全局默认注入(编码前思考/简洁优先/精准修改/目标驱动) |

**编码宪法豁免机制（设计预留）**：Skill 执行时默认注入 karpathy_v1 规则。若某个 Skill 需临时豁免，可在其 metadata 中声明 `override_karpathy: true`，注入逻辑检查该字段后跳过宪法注入。当前阶段保持全局强制，后续按需开放。

**编码宪法默认启用（v2.4+）**：自 2026-07 起，`karpathy_v1` 编码宪法（编码前思考 / 简洁优先 / 精准修改 / 目标驱动）**全局默认启用**，通过 `_facade.py:_coding_policy_profile()` 中 `AIPLAT_CODING_POLICY_PROFILE_ENGINE` 和 `AIPLAT_CODING_POLICY_PROFILE_WORKSPACE` 环境变量控制，默认值为 `"karpathy_v1"`。此变更影响所有 workspace 和 engine Agent 的代码生成 Skill 执行。临时禁用：`export AIPLAT_CODING_POLICY_PROFILE_WORKSPACE=off`。按需覆盖：`export AIPLAT_CODING_POLICY_PROFILE_WORKSPACE=my_profile`。

##### 规约冲突裁决规则（强制）

5 个 CLAUDE.md 文件（workspace + 4 个子仓库）构成系统规约体系。当不同层级的规约对同一事项的规定存在冲突时，按以下规则裁决：

| # | 规则 | 说明 |
|---|------|------|
| 1 | **执行层级优先** | 子仓库规约（core/infra/platform/management）> 根规约（workspace）> 设计文档（docs/） |
| 2 | **代码优先** | 任何规约声明与代码事实冲突时，以代码事实为准，规约须在 24 小时内同步修正 |
| 3 | **变更同步窗口** | 规约冲突发现后，最晚 24 小时内必须修正至少一方，并在 commit message 中标注 `clause-sync` |
| 4 | **审计兜底** | 每次架构审计（`architecture_guard.sh`）必须检查"根规约 vs 子规约"在关键事项上的一致性 |

**skip_claude_md 使用规范（v2.4+）**：`trace_context["skip_claude_md"] = True` 用于 LLM 调用时跳过 CLAUDE.md + 架构规则注入（~20K 字）。使用场景约束：

| 场景 | 是否允许 | 原因 |
|:---|:---:|:---|
| FDE 澄清对话 (`_clarify()`) | ✅ | 澄清场景聚焦业务问题，架构规则导致 hallucination |
| Prompt-type Skill 执行 | ✅ | Skill 自带 SOP，架构上下文为噪音 |
| Agent ReActLoop / 代码生成 | ❌ 禁止 skip；可用 **slim** | 需要架构规则和编码宪法做决策引导。非编码策略（`coding_policy_profile=off`）走精简注入（`_resolve_claude_md_inject_mode`→slim），禁止按 `output_artifact`/业务 Agent 名推断 skip |
| 检索生成 (RAG) / 材料问答 | ❌ | 需要知识治理和引用规则 |

注入预算（配置驱动，非按 Agent 捷径）：`AIPLAT_CLAUDE_MD_INJECT_MODE=full|slim|off` 可强制；未设时由 `coding_policy_profile` 与是否文件写操作决定。写代码/改仓库时强制 full。

**内容归属规范（v2.5+）**：每段知识在系统中有且仅有唯一归属。同一份 SOP / 输出格式 / 域参考数据禁止出现在两个地方。

| 内容类型 | 唯一归属 | 反例（禁止） |
|---------|------|------|
| Agent 的执行步骤与决策逻辑 | `AGENT.md` 的 `system_prompt` + SOP body | workflow JSON 的 `config.prompt` |
| Skill 的输出格式 / 反模式 / 输入约束 | `SKILL.md` 的 SOP + 输出格式 / 反模式章节 | Agent 的 AGENT.md |
| 域级配置数据（通过率、可用域列表、成熟度） | `~/.aiplat/ontologies/{domain_id}.yaml → `DomainRouter.classify()` 运行时读取 | 硬编码在 prompt / 代码字符串中 |
| 运行时上下文（客户信息、部署模式、上游产出物） | `pipeline_state` 透传 | 模板变量 `{{placeholder}}` |
| Workflow 阶段级附加指令 | `PipelineStageConfig.prompt_extra` | JSON 的 `config.prompt` |
| LLM prompt 模板正文 | `prompt_loader._register("id", "...")` | 代码或 JSON 中内嵌 >1 行 prompt 字符串 |

**核心系统修改自检规则（v2.5+）**：修改 `core/harness/`、`core/apps/`、`core/schemas_`、`core/api/core_facade.py` 等共享模块时，必须在 diff 阶段执行以下自检：

| # | 检查项 | 验证方法 |
|---|------|------|
| 1 | 新逻辑是否硬编码了业务概念（域名/Agent名/角色名）？ | `grep -n 'domain_id ==\|agent_id ==\|_TARGET' <changed_files> → 应为空 |
| 2 | 新行为是否可用已有 `PipelineStageConfig` 字段驱动？ | 检查是否引入了新的 `if/elif` 条件链 |
| 3 | 修改是否改变了共享接口的签名或语义？ | `git diff` 检查所有 `def`/`async def` 的函数签名 |
| 4 | 是否需要更新本规范的对应章节？ | 对照上方 "内容归属规范" 表格逐项核对 |
| 5 | 降级/回退路径是否保留？ | 新增路径应保留原有路径作为 `except` 或 `if None` 的 fallback |
| **违反后果**：PR review 阶段发现违反 → 退回修改；合并后发现违反 → `architecture_guard.sh` 记录为违规 |

**业务应用模块目录规范（v2.5+）**：每个业务应用模块（FDE/Builder/Workbench/Value/Learning 等）有且仅有唯一的目录归属。详见 `docs/architecture/plans/app-module-layout.md`。

| 文件类型 | 正确目录 | 禁止位置 |
|---------|------|------|
| REST 端点 (`@router.get/post`) | `aiPlat-platform/apps/{module}/api/` | `core/api/routers/` |
| 无 HTTP 依赖的业务逻辑 | `aiPlat-core/core/apps/{module}/service/` | `core/harness/` |
| 模块 Prompt 模板 | `aiPlat-core/core/apps/{module}/prompts/` | `core/harness/utils/prompt_loader.py` |
| Harness 层代码硬编码模块名 | ❌ 禁止 | 应通过 `DomainRouter` 动态发现 |
| 新模块注册 | `aiPlat-platform/registry/apps.yaml` | 不应在代码中硬编码模块列表 |

**强制规则——代码变更必须同步文档**：

| # | 代码变更类型 | 必须更新的文档 |
|---|------------|--------------|
| 1 | 新增公共类/函数/模块/端点 | `AIPLAT_CAPABILITIES.md` 对应子系统增加一行 |
| 2 | 能

…

_(节选；全文见权威源)_


**节选自** [`AIPLAT_ROADMAP.md`](../../AIPLAT_ROADMAP.md)：

### aiPlat 商业化演进终极作战手册

> 基线：代码交叉验证 | 能力计数见 AIPLAT_CAPABILITIES.md 统计表 | 6/6 syntax,5/5服务健康,架构守卫0违规,全域诊断14项,路径标准化158条
> 对标：Hermes Agent · Claude Code · OpenClaw · Octo (明略科技)  
> 定位：**企业级 FDE 操作系统**（Agent 协作网络 + Spec 生命周期管理）
> 
> **当前能力全貌**：参见 [`AIPLAT_CAPABILITIES.md`](./AIPLAT_CAPABILITIES.md)（当前计数见该文件）
> 
> **最新更新 (2026-07-19)**：P0-P3 hermès-agent 全量吸收 + L6升级三步 + MoA多模型推理。当前计数见 AIPLAT_CAPABILITIES.md。

---

#### 一、基线诊断（来自 `AIPLAT_CAPABILITIES.md` 代码交叉验证，当前计数见该文件统计表）

| 维度 | 评分 | 关键发现 |
|------|:---:|------|
| **Harness 内核** | **A+** | ReAct循环 + 14 Hook + LangGraph checkpoint/resume + Pipeline引擎 + 5级压缩 + 工具输出预算帽 + PatternCache + EmbeddingBridge |
| **记忆子系统** | **A+** | 四层架构 (Working→Episodic→Semantic→TaskSkills) + 软删除动态续期 + 投毒防御字段 + Episodic预评分 + critical_episodes + 每日后台清理 |
| **知识引擎** | **A+** | 本体13步管线 + GraphIndex/HyperEdge + StateMachine + KnowledgeSynthesizer + Palantir 9项对齐 + 多域本体 |
| **企业治理** | **A** | 172 arch_guard规则 + Skill Lint 10规则 + 三层多租户 + 诊断检查 + ComplianceChecks + CapabilityConvergence |
| **基础设施** | **A** | Multi-backend cache/vector/messaging/database/storage + 模型健康检查/质量验证/延迟追踪 + 本地模型自动发现 |
| **Agent 系统** | **A** | 7种实现类 + DynamicRouter(LLM路由) + SubAgent协调器 + ParallelExecutor + 四角色协作体系 |
| **Skill 系统** | **A** | SkillOpt双通道分析 + Rejected Edit Buffer + edit learning rate + effects副作用声明 + semver回滚 + AutoLearner + EvolutionEngine 12步夜间进化 |
| **MCP 协议** | **A** | JSON-RPC 2.0 + HTTP/SSE服务 + Stdio传输 + ClientManager + Runtime + ProductionPolicy |
| **Gate 系统** | **A** | ContextGate/SchemaGate/ResilienceGate/TraceGate/SandboxGate + PolicyGate + ApprovalGate 双门禁 + CircuitBreaker |
| **评估系统** | **A** | EvaluationRunner + HallucinationTracker + RAG Evaluator + DriftDetector + AB Optimizer + CoverageGate + GraphDiff + CodeTestReward |
| **RAG 检索** | **A** | CRAG 3级回退 + HyDE + RRF三路融合 + Graph Early Exit + SemanticCache版本化 + CircuitBreaker + DomainRouter + DocumentConverter协议化 |
| **产品体验** | **A-** | FDE Dashboard 4卡+时间轴 + SpecDetail 3Tab+Revise+Matter + UserWorkbench增强 + OnboardingWizard→Spec联动 + 训练监控 + VS Code插件(已打包.vsix) |
| **自进化能力** | **A** | SpecLifecycle 版本状态机 + FeedbackRadar 5类信号→Spec建议 + TraceVisualizer 决策痕迹 + EvolutionEngine Step13 SpecHealth + SFT→RL桥接 |
| **可观测性** | **A+** | trace_id/span_id + PipelineTrace + 10项Prometheus + 诊断25类(含14项全域测试) + FDE Dashboard + CoT自动注入 + 内联自纠错 |
| **安全合规** | **A-** | ImmuneMemory三级渐进拦截 + CircuitBreaker熔断 + 注入防护 + 投毒防御 + PII检测 + 对象级/字段级权限 + Ed25519签名 + SecretsManager |
| **成本控制** | **A** | 本地模型Ollama + 零LLM分类 + 5级压缩 + 工具输出预算帽 + 语义缓存版本化 + Multi-backend存储 + RewardTuner多目标EMA调权 |
| **编排层** | **A+** | 5 routing_modes (static/llm/debate/swarm/roundtable) + DynamicRouter + Reducer + DebateState收敛 + Swarm竞选择优 + Roundtable平等讨论 + 业务价值系统 |
| **训练管道** | **A** | SFT→RL完整桥接 + TrajectoryScorer四维评分 + 混合采样 + 可模仿性过滤 + RLOOUpdater + Online Rollout + 训练监控前端 |
| **综合评分** | **99/100** | **FDE 操作系统 (A+) + 5 routing_modes (A+) + Spec 生命周期 (A) + 全域诊断 (A+) + 核心 Skills (A)** |

---

#### 二、执行路线图

```
2026 Q3              Q4                 2027 Q1           Q2
Jul Aug Sep | Oct Nov Dec | Jan Feb Mar | Apr May Jun

Phase 0: 紧急止血 (✅ 已完成)
├─ 0.1 PII脱敏  ✅
├─ 0.2 OTel     ✅  
└─ 0.3 语义缓存  ✅

Phase 1: 铸造利刃 (✅ 已完成)
├─ 1.1 SDK      ✅ (基础就绪, SDK包待完善)
├─ 1.2 FanOut   ✅ (ParallelExecutor + DynamicRouter)
└─ 1.3 VS Code  ✅ (已编译 + .vsix 7.9KB 打包)

Phase 2: 自进化 (✅ 已完成)
├─ 2.1 自学习   ✅ (AutoLearner全接线 + SkillOpt双通道 + PatternAccumulator)
├─ 2.2 溯源     ✅ (ProvenanceTracker + context snapshot)
└─ 2.3 企业网关  ✅ (EnterpriseGateway飞书/企微/Slack)

Phase 3: 企业级 (✅ 已完成)
├─ 3.1 四角色体系  ✅ (员工/保安/顾问/协调员 + KPIAgent + StrategyAgent)
├─ 3.2 SFT→RL管线 ✅ (TrajectoryScorer + 混合采样 + 可模仿性 + RLOO + Online Rollout)
├─ 3.3 实时异常感知  ✅ (ToolDriftDetector + ImmuneMemory + CircuitBreaker 三层闭环)
├─ 3.4 业务价值系统  ✅ (五维ROI + 三受众翻译 + GoalAwareRouter + 月度通知)
└─ 3.5 入驻+终端    ✅ (OnboardingWizard 7步 + UserWorkbench + ValueCenter 8页面)

Phase 4: FDE 操作系统 (✅ 已完成 — 本会话)
├─ 4.1 Spec 生命周期  ✅ (SpecLifecycle DRAFT→PENDING→EXECUTING→REVIEW→STABLE→ARCHIVED)
├─ 4.2 用户反馈翻译  ✅ (FeedbackRadar 5类信号→Spec调整建议)
├─ 4.3 决策痕迹可视化 ✅ (TraceVisualizer 犹豫/重复/异常→Spec 建议)
├─ 4.4 FDE 仪表板      ✅ (4卡聚合+时间轴+筛选联动+种子Demo)
├─ 4.5 全域诊断        ✅ (14项检查: 5条旅程 + 5 routing_modes)
├─ 4.6 核心 Skills      ✅ (CoT模板化注入 + 内联自纠错 + Debate/Swarm/Roundtable)
├─ 4.7 合规审计修复    ✅ (agent list_all + shell agents + env-legacy标记)
└─ 4.8 Matter 验收      ✅ (交付物定义 + 验收标准 + SpecDetail revise 增强)

Phase 5: 竞品借鉴（✅ 已完成 — 本会话）
├─ 5.1  MCP 工具延迟加载   ✅ (启动仅加载名称, Schema按需获取)
├─ 5.2  Prompt Caching      ✅ (cache_control注入 + SHA256跨会

…

_(节选；全文见权威源)_


**节选自** [`docs/research/architecture-evolution-roadmap.md`](../research/architecture-evolution-roadmap.md)：

### aiPlat 架构演进路线图（基于 §19 架构对比）

> **依据**：《aiPlat核心能力对标报告.md》§19 架构对比分析（四系统架构面 8 维度对比）+ 本仓库代码现状实测 + 既有架构文档（`docs/architecture/plans/` 的 worker-split-plan 等先例）
> **原则**：渐进式演进（参考 worker-split-plan 的"当前不拆分、触发条件驱动"哲学）；每次演进必须保留向后兼容与回退路径（CLAUDE.md §核心系统修改自检规则 5）；每阶段含代码证据、目标架构特征、任务清单、验收标准
> **目标架构愿景**：在保持"分层单体 + 治理内核 + 多服务部署"定位不变的前提下，向 DSH 的"单一真相源"与"可替换性"演进，同时消化历史耦合，最终形态 = **可治理的分层内核 + 事件可重放的状态层 + 白名单化的扩展缝**
> **2026-08-19 状态更新**：行动纲领 **53 DONE / 0 PARTIAL / 0 OPEN**（54 项核对、53 项有效）；改进方案 **P0/P1/P2 全部落地**；宪法测试 **143 passed**（全绿）；能力数 **1032/1039**（`capability_registry.yaml` total=1032 / `AIPLAT_CAPABILITIES.md` total=1039）；架构守卫 0 ERROR。**本路线图 Phase 0-4 已基本全部落地**（对应行动纲领 P0-A 架构合规 10/10、P1-A 对标差距 6/6、P1-B 体系补全 13/13、P2 演进治理 12/12），各阶段已标注 ✅ 状态与代码证据；仅 Phase 0.2（`coupling_metrics.py` 工具本身）与 0.3（BOUNDARY.yaml 全量审计）未见基线独立证据，如实标注 ⚠️ 待确认。**路线图正文保留为历史计划（2026-08-15 制定），供演进路径回溯**；各阶段"任务/验收"为当时设计，落地情况见每阶段顶部状态标注与文末《落地核对表》。

---

#### 阶段总览

```
Phase 0（基线固化）✅ → Phase 1（状态/事件一致性）✅ → Phase 2（扩展缝）✅ → Phase 3（耦合治理）✅ → Phase 4（架构验证闭环）✅（常态化）
     1-2 周                          2-3 周                  2-3 周              3-4 周                 持续
     「把现状钉住」                  「向单一真相源演进」      「把扩展点白名单化」     「消化历史耦合」        「守卫/宪法/度量常态化」
```

> **2026-08-19 落地状态**：Phase 0-4 已按行动纲领 **53/53 DONE** 全部落地（P0-A 架构合规 10/10、P1-A 对标差距 6/6、P1-B 体系补全 13/13、P2 演进治理 12/12，改进方案 P0-1~P0-5/P1-1~P1-6/P2-1~P2-7 全部落地）。各阶段标注 ✅ = 已验证落地（附代码证据）；⚠️ = 对应任务未见基线独立证据（如实标注，见各阶段）。

每个 Phase 可独立交付、独立回退，不阻塞主线迭代——该设计原则在落地中保持（各阶段改动均保留回退路径，如 Phase 1 默认仍走状态快照）。

---

#### Phase 0：架构基线固化（1-2 周）—— ✅ 已完成（2026-08-19）

> **落地状态**：0.1 已落地（✅），0.2/0.3 ⚠️ 未见基线独立证据（ratchet 门禁机制已由 P2-B2 建立）。对应行动纲领：P0-A4/A6/A7/A8/A9（platform_function_boundary / ast_business_keys / system_prompt_flow / sysgraph_registration 全绿 + §57 0 违规）+ P2-B2（--write-baseline review 门禁）。

**目标**：把当前架构事实"钉住"——消除守卫误报、建立耦合度量基线、补齐 BOUNDARY 声明，使后续演进有可信的"前测"。

##### 0.1 修正守卫自身误报（对应改进方案 P2-4）—— ✅ 已完成

- **现状证据**：§73 报 6 项 wiring info（error_reflector/hallucination_tracker/parallel_executor/enterprise_gateway/implicit_feedback/evolution_nightly_cron "未接线"），实测均误报：
  - `on_error_reflector` 已注册为默认 hook（`hook_manager.py:619` POST_OBSERVE）
  - `evolution_nightly_cron` 已接线（`server.py:1723-1760`）
  - `implicit_feedback` 已被消费（`feedback_radar.py:527`、`agents.py:769`）
  - 守卫检测用字符串搜索（`sys_skill_call`/`server.py startup`），对"经其他路径接入"的模块误报（CLAUDE.md §16-Z 已注明此类历史）
- **任务**：
  1. 修改 `arch_guard_rules.yaml` §73 相关规则（`grep_forbidden`/`grep_required` → 增加豁免声明识别，或改为"grep 到接线点 OR 文件头有 `noqa: wired-via-<path>` 注释"双条件）
  2. 对真实接入路径补 `noqa: wired-via-*` 注释（hook_manager/server.py/feedback_radar）
  3. 确认守卫报 `ok: True`
- **验收**：`python scripts/architecture_guard.py --json` → `ok: True`；6 项 info 全部消除（不再有噪音淹没真实违规）
- **✅ 落地核对（2026-08-19）**：架构守卫 `architecture_guard.sh` 全绿（0 ERROR）；行动纲领 P0-A6（ast_business_keys 绿，R4 正则 + engine_state_keys 基线）/ P0-A7（system_prompt_flow 绿）/ P0-A8（sysgraph_registration 绿）/ P0-A9（§57 0 违规）全部 DONE；CLAUDE.md §19.1"边界守卫 9 errors, 4 warnings → 0 issues"。守卫噪音问题已解决，真实违规可被捕获。

##### 0.2 建立耦合度量基线 —— ✅ 已闭环（2026-08-25）

> **2026-08-19 复核**：`scripts/coupling_metrics.py` 未见基线独立证据（2026-08-19 基线未单列）；但"基线 ratchet 门禁"机制已由 **P2-B2（--write-baseline review 门禁）** 建立（review 时对比 baseline，仅允许下降）。耦合实降目标由 **P0-A1（harness→apps 收敛 DI，宪法白名单 38→25）+ P0-A2（api→CoreFacade，54 文件 292 行 harness 直导清零）+ P2-A4（pipeline_engine 12281→8288 行拆分）** 达成。

- **现状证据**：CLAUDE.md（aiPlat-core）要求"真实降低 `avg_degree` 与'非聚合点 max_degree'"，但 `scripts/` 下**无耦合度量工具**（avg_degree 已在代码中计算（cross-import 分析），coupling_metrics.py 独立工具仍缺（REAL 保留））
- **任务**：
  1. 新增 `scripts/coupling_metrics.py`：AST 扫描 core 下每个 .py 的 import 依赖，输出 `avg_degree`（平均入边+出边）、`max_degree`、top-20 高耦合模块、非聚合点 max_degree（排除已知聚合点如 core_facade/integration）
  2. 跑出基线快照 → `scripts/baselines/coupling_baseline.json`
  3. 接入 `architecture_guard.sh`（ratchet 模式：新提交不得高于基线，仅允许下降）
- **验收**：
  ```bash
  python3 scripts/coupling_metrics.py --baseline scripts/baselines/coupling_baseline.json
  # 预期输出基线 OK + 0 新违规；重复运行结果一致（确定性）
  ```

##### 0.3 BOUNDARY.yaml 补齐审计 —— ✅ 已闭环（2026-08-25）

> **2026-08-19 复核**：BOUNDARY.yaml 全量目录审计未见基线独立证据；但边界类检查已全绿——**P0-A4（platform_function_boundary 绿）** + 宪法 `test_platform_function_boundary`（143 passed 组成之一）+ 架构守卫 §5.7/§80 边界规则 0 违规。

- **现状证据**：`core/harness/BOUNDARY.yaml` 存在（layer: core + known_debt）；但 core 内其他子目录（execution/knowledge/memory/gates 等）是否都有 BOUNDARY 声明未全量核实
- **任务**：`scripts/validate_rules_paths.py` 扩展或新增检查：core 下每个一级子目录（harness 内）必须有 BOUNDARY.yaml（声明 layer + 依赖方向 + known_debt）
- **验收**：`bash scripts/architecture_guard.

…

_(节选；全文见权威源)_


#### 3.3.8 开发视图

**尽调问题**：代码组织、模块边界、构建与本地上手路径？

**权威源**： [`docs/manuals/getting-started.md`](../manuals/getting-started.md) · [`docs/architecture/plans/app-module-layout.md`](../architecture/plans/app-module-layout.md) · [`docs/DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md) · [`CLAUDE.md`](../../CLAUDE.md)（层边界 / 内核无关）

**节选自** [`docs/manuals/getting-started.md`](../manuals/getting-started.md)：

### aiPlat 快速入门指南

> 15 分钟从零启动到运行第一个 Agent。

#### 前置条件

- Python 3.11+
- pip
- 至少一个 LLM API Key (DeepSeek/OpenAI/Qwen 等)

#### Step 1: 克隆与安装 (2 分钟)

```bash
git clone https://github.com/zhuxiangqun/aiPlatform.git
cd aiPlatform
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
pip install -e aiPlat-core/ aiPlat-infra/ aiPlat-platform/ aiPlat-management/
```

#### Step 2: 配置 API Key (1 分钟)

```bash
export DEEPSEEK_API_KEY="sk-your-key-here"
### 或 OpenAI:
export OPENAI_API_KEY="sk-your-key-here"
```

#### Step 3: 启动服务 (2 分钟)

```bash
./start.sh
```

服务启动后：

| 端口 | 服务 | 用途 |
|:---|:---|:---|
| 8000 | Management | API 网关 + 诊断面板 |
| 8001 | Infra | 模型管理 + 基础设施 |
| 8002 | Core | Agent 引擎 + Pipeline |
| 8003 | Platform | 知识库 + Builder |

#### Step 4: 验证安装 (1 分钟)

```bash
### 健康检查
curl http://localhost:8000/api/diagnostics/health/all

### 运行验证脚本
bash scripts/verify-l4-pyramid.sh
### → 预期: L5 (元循环工程)
```

#### Step 5: 运行第一个 Agent (3 分钟)

```bash
### 列出可用 Agent
curl http://localhost:8000/api/core/workspace/agents

### 执行一个 Agent 任务
curl -X POST http://localhost:8000/api/core/workspace/agents/materials_chat/execute \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"用三句话解释 L4 循环工程是什么"}]}'
```

#### Step 6: 查看诊断面板

浏览器打开 `http://localhost:8000/docs` → 查看全部 API 文档。

```bash
### 架构守卫检查
curl -X POST http://localhost:8000/api/diagnostics/guard/run

### 全量诊断
curl -X POST http://localhost:8000/api/diagnostics/run-all
```

#### 下一步

管理端 UI（`./start.sh` 后通常为前端端口，如 `http://localhost:5173`）：

| 你要做的事 | 打开 |
|------------|------|
| 建域 / 改说明书 / 提案 apply | **知识 → 业务本体** `/knowledge/business` |
| 文档入库与检索 | **知识 → 知识库** `/knowledge/library` |
| 一句话生成应用 | **AI 应用工厂** `/app/factory` |
| FDE 现场八步交付 | **FDE 工作台** `/diagnostics/fde` |
| it-ops 组织试点 / 签收准备 | **组织试点** `/org/pilot` |

操作手册入口：[`manuals/README.md`](README.md) · 合册 [`../contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md`](../contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md) · Org [`../contracts/ORG_L5_RUNBOOK.md`](../contracts/ORG_L5_RUNBOOK.md)。

- [API Reference](api-reference.md) — 完整 API 文档（若仓库内仍保留）
- [自主性评估报告](../framework/aiplat-complete-assessment.md) — 系统能力评估
- [验证协议](../framework/verification-protocol.md) — 独立复现验证

#### 常见问题

**Q: 启动失败？**
```bash
### 检查端口占用
lsof -i :8000 -i :8001 -i :8002 -i :8003
kill <PID>
```

**Q: Agent 执行返回错误？**
```bash
### 检查 API Key
echo $DEEPSEEK_API_KEY
### 查看日志
tail -f ~/.aiplat/logs/core.log
```

**Q: 如何升级？**
```bash
git pull origin main
./start.sh  # 重启服务
```


**节选自** [`docs/architecture/plans/app-module-layout.md`](../architecture/plans/app-module-layout.md)：

### 业务应用模块目录规范 v1.0

#### 适用范围

FDE、Builder、Workbench、Value、Learning、Prompt Management 等所有业务应用模块。

#### 核心原则

> 每个业务应用模块有且仅有唯一的目录归属。模块的 REST API、业务逻辑、域名本体、Prompt 模板各自归入正确的架构层。

#### 标准目录结构

```
{module_name}/
├── api/                    ← REST/GraphQL 端点定义
│   ├── __init__.py
│   ├── routers.py          ← @router.get / @router.post 等
│   └── schemas.py          ← Pydantic 请求/响应模型
├── service/                ← 业务逻辑（无 HTTP 依赖）
│   ├── __init__.py
│   └── {module}_service.py
├── domain/                 ← 域本体定义 + 种子数据
│   ├── {module}.yaml       ← 本体类定义
│   └── seed.json           ← 种子数据
├── prompts/                ← LLM prompt 模板（模块自管）
│   └── prompts.py
├── skills/                 ← 模块专用 Skill（SKILL.md 或 Python 类）
│   └── {skill_name}/
│       └── SKILL.md
└── agents/                 ← 模块专用 Agent 定义
    └── {agent_name}/
        └── AGENT.md
```

#### 分层归属规则

| 文件类型 | 放在哪一层 | 目录路径 |
|---------|:---:|------|
| `@router.get/post` 端点定义 | **Platform** | `aiPlat-platform/apps/{module}/api/` |
| 无 HTTP 依赖的业务逻辑（Agent调用、状态管理） | **Core** | `aiPlat-core/core/apps/{module}/service/` |
| 域本体 YAML + 种子数据 | **Config** | `~/.aiplat/ontologies/` + `~/.aiplat/seed_data/` |
| LLM prompt 模板 | **Module self-managed** | `aiPlat-core/core/apps/{module}/prompts/` |
| 模块专用 Skill | **Core Engine** | `aiPlat-core/core/engine/skills/` 或模块自管 |
| 模块专用 Agent | **Workspace** | `~/.aiplat/agents/` |

#### 注册机制

模块通过在 `aiPlat-platform/registry/apps.yaml` 中声明来注册自身：

```yaml
modules:
  fde:
    name: "FDE 现场交付引擎"
    description: "Field Deployment Engineer — 客户诊断与交付工作台"
    api_prefix: "/api/platform/apps/fde"
    api_module: "api.routers"
    service_module: "core.apps.fde.service"
    prompts_module: "core.apps.fde.prompts"
    domains: ["fde-delivery"]
    agents: ["fde_business_analyst", "fde_solution_architect", "fde_delivery_engineer", "fde_delivery_manager"]
    skills: ["customer_profile_creator", "domain_assessor", "field_assessment", "package_builder", "acceptance_checker", "poc_data_inject"]
```

Core 通过读取此注册表动态发现模块，而不是在代码中硬编码模块名称。

#### 反模式（禁止）

| ❌ 禁止 | ✅ 应该 |
|--------|--------|
| 模块的 REST 端点定义在 `core/api/routers/{module}.py` | 放在 `platform/apps/{module}/api/routers.py` |
| 模块的 Prompt 模板注册在 `core/harness/utils/prompt_loader.py` 中 | 放在 `core/apps/{module}/prompts/`，由模块自行注册 |
| Harness 层代码硬编码 `module_name` 作为域标识 | 通过 `DomainRouter` 动态发现所有已注册域 |
| 模块之间的跨模块调用绕过 Facade | 通过注册表声明的公开接口调用 |

#### 迁移优先级

当新模块首次创建时，遵循此规范。现有模块按以下优先级渐进迁移：

| 批次 | 模块 | 理由 |
|:---:|------|------|
| **星** | **FDE** | 改动最频繁，痛点最明确，作为迁移样板 |
| A | Builder（流水线/工作流） | 与 FDE 耦合最紧 |
| B | Workbench / Overview / Kanban | 用户工作台相关 |
| C | Value / Roles / Safety | 价值评估与权限 |
| D | Learning / Finetune | 学习训练相关 |
| E | Prompt 管理 / Evaluations | Prompt 工具链 |
| F | 其他（code_intel / browser_test 等） | 低频变更模块 |

#### 验收标准

```bash
### core/api/routers/ 下无应用模块路由器
ls aiPlat-core/core/api/routers/fde*.py 2>/dev/null
### → 空（或仅含重定向 stub）

### Harness 层无业务模块硬编码
grep -rn "fde-\|builder\|workbench" aiPlat-core/core/harness/ --include='*.py'
### → 空

### 新模块通过 apps.yaml 注册
python3 -c "import yaml; print(yaml.safe_load(open('aiPlat-platform/registry/apps.yaml')))"
### → 包含 fde 模块条目
```

#### 参考

- 四层架构定义：`docs/index.md` §Layer 0-3
- 层边界标准：`docs/architecture/boundary-standard.md`
- 系统架构契约：`docs/architecture/system-architecture-contract.md`
- 内容归属规范：`CLAUDE.md` §8
- 核心修改自检规则：`CLAUDE.md` §8


**节选自** [`docs/DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md)：

### aiPlat 文档系统治理框架

> 本文档是 aiPlat 文档系统的"宪法"——定义目录结构、文档类型、边界规则、单一真相源映射和维护流程。
> 所有其他文档必须在本框架的约束下创建、维护和归档。

---

#### 一、目录结构

```
workspace-root/
│
├── CLAUDE.md                          ← 工作区兜底规约（AI 编程行为约束）
├── AIPLAT_CAPABILITIES.md            ← 唯一能力清单（当前计数见该文件统计表）
│                                      ↑ docs/whitepaper/aiplat-platform-status-whitepaper.md
│                                        由此生成（scripts/generate_platform_whitepaper.py）
├── AIPLAT_ROADMAP.md                 ← 商业化路线图（评分 + 基线）
├── README.md                         ← 部署手册
│
├── docs/
│   ├── DOCUMENT_SYSTEM.md            ← 本文档 — 文档系统治理框架
│   ├── README.md                     ← 唯一导航入口（合并原 index.md）
│   │
│   ├── project/                       ← 项目管理
│   │   └── PHASE_STATUS.md           ← Phase 实施状态快照
│   │
│   ├── manuals/                      ← 🆕 统一操作手册目录（所有面向角色的手册入口）
│   │   ├── README.md                  ← 手册目录索引（按角色推荐）
│   │   ├── getting-started.md         ← 快速入门
│   │   ├── management.md              ← 管理画面操作手册
│   │   ├── ontology.md                ← 本体模型管理手册
│   │   ├── deployment.md              ← 部署指南
│   │   ├── development.md            ← 开发指南
│   │   ├── testing.md                ← 测试指南
│   │   ├── deploy-guide.md           ← 部署速查
│   │   ├── engineering-quality.md    ← 工程质量
│   │   ├── production-readiness.md   ← 生产就绪
│   │   ├── wiki-fts5-analysis.md     ← Wiki 分析
│   │   └── fde/                       ← FDE 交付体系（4 个手册 + 导航 + 模板 + 实例，旧版归档于 _archive）
│   │
│   ├── architecture/                 ← 架构设计
│   │   ├── overview.md               ← 权威架构全景（唯一出处）
│   │   ├── boundary-standard.md      ← 层边界判定标准
│   │   ├── core-layer1-latest.md     ← Core 层最新架构详述
│   │   ├── system-architecture-contract.md ← 跨层契约
│   │   ├── role_system.md            ← 角色体系
│   │   └── decisions/                ← 架构裁决记录 (ADR)
│   │       ├── evaluator_calibration.md
│   │       └── tot_reserve.md
│   │
│   ├── design/                       ← 设计文档（To-Be / Plan）
│   │   ├── ontology-design.md         ← 本体框架设计
│   │   ├── knowledge-ontology-plan.md ← 知识本体模型
│   │   ├── model-management.md        ← 模型管理设计
│   │   ├── ui-design.md               ← UI 设计规范
│   │   └── ui-implementation-status.md ← UI 实施状态
│   │
│   ├── framework/                     ← 成熟度评估框架
│   │   ├── aiplat-autonomy-framework.md
│   │   ├── aiplat-complete-assessment.md
│   │   ├── assessment-scores.json     ← 唯一评估分数源
│   │   └── ...（8 个文件）
│   │
│   ├── security/                      ← 安全架构与测试
│   │   ├── security-architecture.md
│   │   ├── security-testing.md
│   │   └── ...（4 个文件）
│   │
│   ├── API/                           ← API 协议与契约
│   │   ├── api-reference.md
│   │   └── AttributionSchema.md
│   │
│   ├── policy/                        ← 安全/运维策略
│   │   ├── external-allowlist.md
│   │   └── mcp-stdio-prod-allowlist.md
│   │
│   ├── standards/                     ← 跨层规范（强制性）
│   │   ├── 规范-core-run_id-trace_id-request_id.md
│   │   ├── 规范-platform-鉴权与身份透传.md
│   │   └── 规范-app-session_id与conversation_key.md
│   │
│   ├── agents/                        ← Agent 架构设计
│   │   └── subagent.md
│   │
│   ├── mcp/                           ← MCP 协议集成
│   │   └── index.md
│   │
│   ├── skills/                        ← Skill 动态进化
│   │   └── evolution.md
│   │
│   ├── tools/                         ← 工具系统增强
│   │   └── enhancement.md
│   │
│   ├── whitepaper/                    ← 白皮书
│   │   ├── aiplat-l4-autonomy-assessment-v1.0.0.md
│   │   └── verification-protocol.md
│   │
│   ├── strategy/                      ← 战略分析 / 竞品对比
│   │   └── comparison-vs-vendors.md
│   │
│   ├── reports/                       ← 生成报告（不手动编辑）
│   │   ├── README.md
│   │   ├── AIPLAT_ARCHITECTURE_REPORT.md
│   │   └── AIPLAT_DIAGNOSTIC_REPORT.md
│   │
│   ├── harness/                       ← 跨仓库 Harness 索引
│   │   └── README.md
│   │
│   ├── audit/                         ← 合规审计
│   │   └── compliance-matrix.md
│   │
│   ├── compliance/                    ← 法规合规评估
│   │   └── eu-ai-act-assessment.md
│   │
│   ├── articles/

…

_(节选；全文见权威源)_


#### 3.3.9 集成架构

**尽调问题**：MCP / A2A / 外部适配与生产允许列表？

生态细节与协议切片见分卷 04；此处给出运行时集成入口。

**权威源**： [`docs/mcp/index.md`](../mcp/index.md) · [`docs/policy/mcp-stdio-prod-allowlist.md`](../policy/mcp-stdio-prod-allowlist.md)

**节选自** [`docs/mcp/index.md`](../mcp/index.md)：

### MCP 协议集成设计

#### 概述

本文档描述如何将 Model Context Protocol (MCP) 集成到 aiPlat-core 系统，使系统能够连接外部 MCP 服务器并使用其提供的工具。

#### 目标

1. **连接外部 MCP 服务器** - 支持 stdio 和 SSE 传输
2. **工具接入** - 将 MCP 工具转换为本地 ITool 接口
3. **工具导出** - 将本地工具暴露为 MCP 服务器

#### 架构设计

##### 模块结构

```
core/apps/mcp/
├── types.py       # 协议数据类型定义
├── protocol.py    # JSON-RPC 处理、SSE/stdio 传输
├── client.py      # MCP Client 和 ClientManager
├── adapter.py     # 工具适配器 (MCP ↔ ITool)
├── server.py      # MCP Server (FastAPI)
└── config.py      # 配置管理
```

##### 核心组件

###### 1. 类型定义 (types.py)

| 类型 | 用途 |
|------|------|
| `JSONRPCRequest` | JSON-RPC 请求 |
| `JSONRPCResponse` | JSON-RPC 响应 |
| `MCPTool` | MCP 工具定义 |
| `MCPToolResult` | 工具调用结果 |
| `MCPResource` | MCP 资源定义 |
| `MCPServerCapabilities` | 服务器能力 |
| `MCPServerConfig` | 服务器配置 |
| `MCPClientConfig` | 客户端配置 |

###### 2. 协议处理 (protocol.py)

- JSON-RPC 2.0 请求/响应编解码
- SSE (Server-Sent Events) 传输
- STDIO 传输

###### 3. 客户端 (client.py)

| 类 | 职责 |
|------|------|
| `MCPClient` | 单个 MCP 服务器连接管理 |
| `MCPClientManager` | 多服务器连接管理 |

###### 4. 适配器 (adapter.py)

| 类 | 职责 |
|------|------|
| `MCPToolAdapter` | MCP 工具 → 本地 ITool |
| `MCPToolExporter` | 本地 ITool → MCP 工具 |
| `MCPClientWrapper` | 批量注册 MCP 工具到注册表 |

#### 使用方式

##### 1. 连接外部 MCP 服务器

```python
from core.apps.mcp import MCPClientManager, MCPClientConfig

manager = MCPClientManager()

### SSE 连接
client = await manager.add_server(
    "my-server",
    MCPClientConfig(
        server_url="http://localhost:3000/mcp",
        transport=TransportType.SSE
    )
)

### STDIO 连接
client = await manager.add_server(
    "filesystem",
    MCPClientConfig(
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/data"]
    )
)
```

##### 2. 注册 MCP 工具到本地注册表

```python
from core.apps.mcp.adapter import MCPClientWrapper

wrapper = MCPClientWrapper(manager)
count = await wrapper.register_server_tools("my-server", tool_registry)
print(f"Registered {count} tools")
```

##### 3. 启动 MCP 服务器（暴露本地工具）

```python
from core.apps.mcp import MCPServer

server = MCPServer(tool_registry)
await server.start(host="0.0.0.0", port=8080)
```

#### 配置

##### 0. 目录化配置（engine vs workspace）

MCP server 的“启用/禁用/策略”推荐以文件系统为真值来源，并按 scope 分离：

- **引擎内置（engine，仅核心能力层使用）**  
  `aiPlat-core/core/engine/mcps/<server>/{server.yaml,policy.yaml}`

- **应用库（workspace，对外/用户可用）**  
  `~/.aiplat/mcps/<server>/{server.yaml,policy.yaml}`

管理面对应两套入口（避免混用）：
- engine：`GET/POST /api/core/mcp/servers*`
- workspace：`GET/POST /api/core/workspace/mcp/servers*`

##### 服务器配置 (MCP Server)

```python
MCPServerConfig(
    name="my-server",
    transport=TransportType.SSE,  # 或 STDIO
    command="python",  # for stdio
    args=["server.py"],
    url="http://localhost:3000",  # for sse
    auth={"type": "bearer", "token": "..."}
)
```

##### 客户端配置 (MCP Client)

```python
MCPClientConfig(
    server_url="http://localhost:3000/mcp",
    transport=TransportType.SSE,
    timeout=30000,  # ms
    auth={"type": "bearer", "token": "..."}
)
```

#### 安全考虑

1. **URL 白名单** - HTTP 工具应配置允许的域名
2. **认证** - 支持 Bearer Token 认证
3. **超时控制** - 防止工具调用挂起
4. **响应大小限制** - 防止过大响应占用内存

#### 待实现

- [ ] STDIO 传输的进程启动和管理
- [ ] MCP 服务器认证
- [ ] 工具缓存和刷新机制
- [ ] 连接池管理


**节选自** [`docs/policy/mcp-stdio-prod-allowlist.md`](../policy/mcp-stdio-prod-allowlist.md)：

#!/bin/false
### prod 放行 stdio MCP（路线A）策略

> 背景：stdio MCP 等同于在 core 所在机器上启动本机进程（高风险 L3）。  
> 目标：在 **prod 也允许使用** 的前提下，提供可审计、可回滚、默认拒绝的显式放行机制。

#### 1) 放行条件（必须同时满足）

当 `AIPLAT_ENV=prod` 时，以下条件必须全部满足，stdio MCP 才允许：

1. `~/.aiplat/mcps/<server>/server.yaml` 的 `metadata.prod_allowed: true`
2. 环境变量 `AIPLAT_PROD_STDIO_MCP_ALLOWLIST` 包含该 `server_name`（逗号分隔）
3. `server.yaml` 的 `command` 为绝对路径，且命令路径前缀在 `AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES` 允许范围内  
   - 该变量支持 `:`（os.pathsep）或 `,` 分隔多个前缀
4. 加固校验（prod 默认启用）：
   - 禁止高风险解释器作为入口命令（默认：`bash,sh,zsh`；可用 `AIPLAT_STDIO_DENY_COMMAND_BASENAMES` 覆盖）
   - 命令必须存在且具备可执行权限（best-effort：`os.path.exists` + `os.access(..., X_OK)`）
   - 参数数量/长度限制（默认：最多 32 个参数、每个参数最多 （参见 AIPLAT_CAPABILITIES.md 当前计数） 字符；可通过 `AIPLAT_STDIO_MAX_ARGS` / `AIPLAT_STDIO_MAX_ARG_LENGTH` 调整）
5. 推荐增强（可选开启）：prod 强制统一 launcher
   - `AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD=true`
   - `AIPLAT_STDIO_PROD_LAUNCHER=/opt/aiplat/mcp/bin/launch`
   - 开启后：`server.yaml.command` 必须与 `AIPLAT_STDIO_PROD_LAUNCHER` 完全一致（避免散落多入口命令）

示例：

```bash
export AIPLAT_ENV=prod
export AIPLAT_PROD_STDIO_MCP_ALLOWLIST="integrated_browser,my_internal_stdio_server"
export AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES="/opt/aiplat/mcp/bin:/usr/local/aiplat/mcp/bin"
export AIPLAT_STDIO_DENY_COMMAND_BASENAMES="bash,sh,zsh"
export AIPLAT_STDIO_MAX_ARGS="32"
export AIPLAT_STDIO_MAX_ARG_LENGTH="512"
export AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD="true"
export AIPLAT_STDIO_PROD_LAUNCHER="/opt/aiplat/mcp/bin/launch"
```

server.yaml 示例：

```yaml
name: my_internal_stdio_server
enabled: false
transport: stdio
command: /opt/aiplat/mcp/bin/my-server
args: ["--config", "/etc/aiplat/mcp/my-server.yaml"]
metadata:
  description: 内部受控 stdio MCP server
  prod_allowed: true
```

使用 launcher 时的 server.yaml 示例：

```yaml
name: my_internal_stdio_server
enabled: false
transport: stdio
command: /opt/aiplat/mcp/bin/launch
args: ["my_internal_stdio_server", "--config", "/etc/aiplat/mcp/my-server.yaml"]
metadata:
  description: 内部受控 stdio MCP server（通过统一 launcher 启动）
  prod_allowed: true
```

#### 2) 受影响的操作

在 prod 中，stdio MCP 的以下操作都会触发同一套放行校验：
- 启用：`POST /api/core/workspace/mcp/servers/{name}/enable`
- 工具发现：`GET /api/core/workspace/mcp/servers/{name}/tools`

若未满足条件，接口返回 403，并在 UI 中提示策略原因。

#### 3) 为什么需要双白名单（server + command 前缀）

- **server_name 白名单**：防止任意人创建新 server 并启用（控制面可控）
- **command 前缀白名单**：防止用 `bash`/`python`/任意路径执行任意代码（执行面可控）

#### 4) 建议（进一步增强）

- 将 `command` 收敛为受控的 launcher（例如 `/opt/aiplat/mcp/bin/launch`），由 launcher 再选择具体子命令
- 配置审计：记录 enable/disable 以及 tools/call 的审计日志（输入输出摘要）
- 资源限制：超时、并发、CPU/内存配额（若支持容器/沙箱更佳）

#### 5) 已落地的审计

当前已将 MCP 管理动作写入 ExecutionStore 的 `syscall_events`（kind=`mcp_admin`）：
- workspace.mcp.upsert
- workspace.mcp.enable / workspace.mcp.disable
- workspace.mcp.discover_tools

用于后续在 Traces/审计页面统一查询与追踪。


#### 3.3.10 质量属性场景（SLA / SLO）

**尽调问题**：可用性分层、误差预算与告警阈值？

与 §3.3.2 共用 `slo.md`；本节强调质量属性目标而非压测脚本入口。

**权威源**： [`docs/architecture/slo.md`](../architecture/slo.md) · [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md)

**节选自** [`docs/architecture/slo.md`](../architecture/slo.md)：

### aiPlat Service Level Objectives

> **Status**: Draft | **Version**: 1.0 | **Owner**: aiPlat Architecture Team

#### Service Tier Definitions

| Tier | Services | Criticality | Target Availability |
|:---|:---|:--:|:--:|
| **Tier 1** | aiPlat-core (API), aiPlat-management (gateway) | Critical — platform unusable without | 99.9% |
| **Tier 2** | aiPlat-infra (LLM/model management) | High — degradation but not full outage | 99.5% |
| **Tier 3** | aiPlat-platform (builder/workflow) | Medium — batch operations, not real-time | 99.0% |

#### SLO Matrix

##### Tier 1: Core + Management (Critical)

| SLI | Target | Measurement Window |
|:---|:--:|:--:|
| **Availability** | ≥ 99.9% | 30 days |
| **Latency (P95)** | ≤ 500ms for agent execute endpoint | 30 days |
| **Error Rate** | ≤ 0.1% of all requests | 30 days |
| **LLM Response Time** | ≤ 30s for non-streaming | 30 days |
| **Pipeline Start Latency** | ≤ 5s from request to execution | 30 days |

##### Tier 2: Infra (High)

| SLI | Target | Measurement Window |
|:---|:--:|:--:|
| **Availability** | ≥ 99.5% | 30 days |
| **Model Health Check** | ≤ 10s response | 5 minutes |
| **Model Discovery Latency** | ≤ 1s to list models | 5 minutes |

##### Tier 3: Platform (Medium)

| SLI | Target | Measurement Window |
|:---|:--:|:--:|
| **Availability** | ≥ 99.0% | 30 days |
| **Builder Session Commit** | ≤ 3s | 30 days |

#### Error Budget

| Tier | Availability | Allowed Downtime (monthly) | Error Budget |
|:---|:--:|:--|:--:|
| Tier 1 | 99.9% | 43.2 minutes | 0.1% |
| Tier 2 | 99.5% | 3.6 hours | 0.5% |
| Tier 3 | 99.0% | 7.2 hours | 1.0% |

#### Alerting Thresholds

| Alert | Condition | Severity | Action |
|:---|:---|:--|:---|
| Tier 1 availability | Error rate > 1% (5 min) | Critical | PagerDuty |
| Tier 1 latency | P95 > 2s (5 min) | Warning | Slack |
| Tier 1 error rate | 50% budget consumed | Warning | Slack + Jira ticket |
| Tier 1 error rate | 90% budget consumed | Critical | PagerDuty |
| Tier 2 availability | Error rate > 5% (5 min) | Warning | Slack |
| Pipeline timeout | > 300s (1 occurrence) | Warning | Slack |

#### Measurement

All SLIs are measured via Prometheus metrics:

| SLI | Prometheus Metric |
|:---|:---|
| Availability | `http_requests_total{status_code!~"5.."}` / `http_requests_total` |
| Latency | `histogram_quantile(0.95, http_request_duration_seconds_bucket)` |
| Error Rate | `http_requests_total{status_code=~"5.."}` / `http_requests_total` |
| LLM Time | `llm_request_duration_seconds` |
| Pipeline Latency | `pipeline_start_latency_seconds` |

#### Review Cadence

| Activity | Frequency | Owner |
|:---|:---|:---|
| SLO review | Monthly | Architecture Team |
| Error budget review | Monthly | Platform Engineering |
| Alert threshold tuning | Quarterly | SRE |

#### Performance Baselines (Measured)

> Numbers collected from aiPlat v0.0.1 running on macOS M1 (local, no GPU). Production numbers will vary.

| Metric | Local (M1) | Target (Production) | Status |
|:---|:---:|:---|:--:|
| Agent execute P50 | ~2s | ≤ 200ms | ⚠️ local LLM bottleneck |
| Agent execute P95 | ~8s | ≤ 2s | ⚠️ local LLM bottleneck |
| Health check latency | <10ms | ≤ 50ms | ✅ |
| Model list latency | <100ms | ≤ 1s | ✅ |
| Pipeline start latency | ~3s | ≤ 5s | ✅ |
| Concurrent health checks | 50 req/s | 500 req/s | ⚠️ not stress tested |
| Wiki search latency | ~500ms | ≤ 1s | ✅ |
| Agent step latency (T1 model) | ~1s | ≤ 500ms | ⚠️ local|

**Stress test**: `bash scripts/stress-test.sh localhost 50 500`
**Continuous tracking**: Prometheus metrics → Grafana dashboard

#### K8s Readiness

Production deployment requires all liveness/readiness probes to pass:

```yaml
### Core service (Tier 1)
livenessProbe:
  httpGet: {path: /api/core/health, port: 8002}
  initialDelaySeconds: 30
  periodSeconds: 15
readinessProbe:
  httpGet: {path: /api/core/health, port: 8002}
  initialDelaySeconds: 15
  periodSeconds: 10
```

**Readiness gate checklist**:
- [ ] Core health endpoint returns 200
- [ ] Infra model list endpoint returns models  
- [ ] Management health/all returns 4-layer healthy
- [ ] Database WAL mode enabled (pool.db)
- [ ] Gossip protocol peers reachable (if multi-AZ)


## 4. 相关横切（对标 / 评级）

完整对标与评级目录见总白皮书 §2.5 与 [`docs/whitepaper/WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md)。

## 5. 验证

```bash
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check
```

*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`tech-architecture`*
