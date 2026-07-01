# aiPlatform 系统架构全景

> 最后更新: 2026-07-01 | 425✅ | 从 `AIPLAT_CAPABILITIES.md` 聚合生成
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
  → HITL 暂停/恢复 → snapshot → 下一阶段 → 完成 → Skill 晶体化

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

完整清单: `AIPLAT_CAPABILITIES.md`（425 项，每项标注代码位置）

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

---

## 六、多系统对标

参见 [`docs/architecture/comparison.md`](comparison.md) — 9 维度 vs Hermes Agent / Claude Code / OpenClaw 深度对比。

---

## 七、从哪里开始读

按时间投入分层：参见 [`docs/README.md`](../README.md)。
