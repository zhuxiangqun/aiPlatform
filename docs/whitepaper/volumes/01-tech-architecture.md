---
title: "aiPlat 技术架构白皮书"
volume_id: tech-architecture
type: whitepaper-volume
status: generated
generated_at: "2026-10-13T01:36:27Z"
audience: "CTO、架构师、平台工程师"
core_question: "为什么这样设计？边界与权衡是什么？"
priority: P0
source_status: ready
suite: docs/whitepaper/whitepaper-suite.yaml
suite_sha256: "0907c52c20c69036b0d8cc541668dabb4d8811d1109716aa545cf27a8ff56a30"
caps_sha256: "e2e1936484e9ca34a1fedaa4193db677b76758c50291c870feca845ce034fc94"
scores_sha256: "96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687"
language: zh-CN
---

<!-- volume_stamp id=tech-architecture suite_sha256=0907c52c20c69036b0d8cc541668dabb4d8811d1109716aa545cf27a8ff56a30 caps_sha256=e2e1936484e9ca34a1fedaa4193db677b76758c50291c870feca845ce034fc94 scores_sha256=96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687 -->

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
| 生成时间 (UTC) | `2026-10-13T01:36:27Z` |
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
| [`docs/knowledge-system.md`](../knowledge-system.md) | 数据 / 知识存储路径 | ✅ |
| [`docs/architecture/knowledge-base-architecture.md`](../architecture/knowledge-base-architecture.md) | 知识库架构 | ✅ |
| [`docs/security/security-architecture.md`](../security/security-architecture.md) | 安全嵌入（技术视角交叉） | ✅ |
| [`docs/manuals/testing.md`](../manuals/testing.md) | 测试金字塔与策略 | ✅ |
| [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md) | 执行质量门禁 | ✅ |
| [`docs/research/architecture-evolution-roadmap.md`](../research/architecture-evolution-roadmap.md) | 架构演进路线 | ✅ |
| [`docs/manuals/getting-started.md`](../manuals/getting-started.md) | 开发上手 | ✅ |
| [`docs/architecture/plans/app-module-layout.md`](../architecture/plans/app-module-layout.md) | 应用模块目录规范 | ✅ |
| [`docs/mcp/index.md`](../mcp/index.md) | 集成 / MCP 入口 | ✅ |


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

参见 [`docs/architecture/comparison.md`](comparison.md) — 18 维度 vs Hermes Agent / Claude Code / OpenClaw / DeepSeek Harness / OpenAI Codex（2026-10）。

---

## 七、从哪里开始读

按时间投入分层：参见 [`docs/README.md`](../README.md)。

> 参见：[私有控制平面 — aiPlat 四层防御体系](articles/private-control-plane.md) 了解更多 PolicyGate/ApprovalGate 的设计细节。


### 3.2 架构对比入口（comparison）

# aiPlat — 六平台深度对标摘要（2026-10）

> **生成/调研时点**：2026-10-13  
> **对标范围**：aiPlat × Hermes Agent × Claude Code × OpenClaw × DeepSeek Harness × OpenAI Codex  
> **细节与证据权威**：[`docs/research/aiPlat核心能力对标报告.md`](../research/aiPlat核心能力对标报告.md) · 底稿 [`docs/research/对标底稿-2026-10-五家.md`](../research/对标底稿-2026-10-五家.md)  
> **本文角色**：架构入口摘要（供白皮书 §3.2 节选）。**禁止**把本文当作第二能力清单；星级须能回溯底稿。  
> 旧四平台稿已归档：[`docs/archive/comparison-four-platform-2026-07.md`](../archive/comparison-four-platform-2026-07.md)

---

## 一、六平台核心定位

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw | DeepSeek Harness | OpenAI Codex |
|:---|:---|:---|:---|:---|:---|:---|
| **定位** | 企业 AI 操作系统（交付流水线 + 治理 + 知识） | 自学习个人/团队 Agent | 终端/IDE agentic coding | 多端个人助手（Gateway） | 一切皆插件的 agent harness | 可嵌入 coding agent 运行时 |
| **语言** | Python | Python + TUI/TS | 闭源引擎（JS 产物） | TypeScript | TypeScript | Rust（`codex-rs`） |
| **协议** | 私有 / 平台 | MIT | 专有引擎 | MIT | 开源（rc） | Apache-2.0 |
| **本轮指纹** | HEAD + CAP 2105 | clone `562fda90` / tag v0.21.7 | npm latest 2.1.296（产物 2.1.70） | pkg/GH **2026.10.2** | 0.1.0-rc.5 @ 47f94385 | GH **rust-v0.162.1**（本地树结构） |
| **架构重心** | Pipeline + Syscall/Gate + 本体/知识 | 单循环 + Gateway + 学习闭环 | Dynamic workflows + hooks | Gateway + Channels + Apps | Cordis 插件 / 事件源 | Thread/Turn + app-server + OS 沙箱 |

---

## 二、18 维度关键能力对标

评分刻度：★★★★★ 该维领先或企业级完备 · ★★★★☆ 强 · ★★★☆☆ 可用 · ★★☆☆☆ 弱/窄 · ★☆☆☆☆ 基本缺失。  
依据见底稿；**非**营销分。

### A. 执行与编排（维 1–4）

| 维 | 能力 | aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex |
|:--:|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | Harness 执行内核 | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★☆☆ | ★★★★☆ | ★★★★☆ |
| 2 | Agent / 多 Agent | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★★☆ | ★★★★☆ | ★★★☆☆ |
| 3 | Skill 系统 | ★★★★☆ | ★★★★★ | ★★★☆☆ | ★★★★☆ | ★★★★☆ | ★★★☆☆ |
| 4 | MCP / 工具扩展 | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★★☆ | ★★★★★ | ★★★★☆ |

**要点**：aiPlat 以 Pipeline + Syscall 治理见长；Hermes Skill/学习生态最开放；DSH 插件纯度高；Codex/CC 偏 coding harness。

### B. 记忆 · 知识 · 提示（维 5–8）

| 维 | 能力 | aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex |
|:--:|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| 5 | 记忆 / 上下文工程 | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★☆☆ | ★★★★☆ | ★★★★☆ |
| 6 | 知识库 / 本体 | ★★★★★ | ★★☆☆☆ | ★☆☆☆☆ | ★★☆☆☆ | ★☆☆☆☆ | ★☆☆☆☆ |
| 7 | RAG / 检索治理 | ★★★★★ | ★★★☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★☆☆☆☆ |
| 8 | 提示词 / Cache 工程 | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ | ★★★★☆ |

**要点**：知识/本体/企业 RAG 仍为 aiPlat 差异化；Hermes/Codex 在压缩与 cache 友好路径上强。

### C. 质量 · 进化 · 治理（维 9–12）

| 维 | 能力 | aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex |
|:--:|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| 9 | 可观测性（平台级） | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★☆☆ |
| 10 | 幻觉 / 质量门 | ★★★★☆ | ★★☆☆☆ | ★★☆☆☆ | ★☆☆☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| 11 | 自演进 / 学习闭环 | ★★★★☆ | ★★★★★ | ★☆☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★☆☆☆☆ |
| 12 | 企业治理（多租户/审计/审批） | ★★★★★ | ★☆☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ |

**要点**：治理与平台级可观测 aiPlat 领先；会话内学习 Hermes 最完整；OpenClaw 明确 **非** 敌意多租户边界（SECURITY）。

### D. 新增工程维（维 13–18 = 计划 D15–D20）

| 维 | 能力 | aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex |
|:--:|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| 13 | 可嵌入 / 协议面（SDK/app-server/A2A） | ★★★★☆ | ★★★★☆ | ★★★☆☆ | ★★★★☆ | ★★★★☆ | ★★★★★ |
| 14 | 原生端与通道广度 | ★★★☆☆ | ★★★★☆ | ★★☆☆☆ | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ |
| 15 | 执行后端与部署拓扑 | ★★★★☆ | ★★★★★ | ★★☆☆☆ | ★★★★☆ | ★★★☆☆ | ★★★☆☆ |
| 16 | 交付 / Spec 生命周期（HITL 流水线） | ★★★★★ | ★★☆☆☆ | ★★★☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| 17 | OS 沙箱与工作树隔离 | ★★★★☆ | ★★★☆☆ | ★★★★☆ | ★★★☆☆ | ★★★☆☆ | ★★★★★ |
| 18 | 评测 / 质量门 / 可观测拆分 | ★★★★★ | ★★☆☆☆ | ★★★☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★☆☆ |

**要点**：通道/原生端 OpenClaw 第一；多终端后端 Hermes 第一；可嵌入与 OS 沙箱 Codex 第一；交付流水线 aiPlat 独有强度。

---

## 三、综合评分矩阵（加权）

权重：维 1,2,5,12,16 各 **8%**；维 3,4,6,7,11,13,17,18 各 **5%**；维 8,9,10,14,15 各 **4%**（合计 100%）。  
星→分：★=20 … ★★★★★=100，再按权加权。

| 维 | aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 执行内核 | 100 | 80 | 80 | 60 | 80 | 80 |
| 2 Agent | 100 | 80 | 80 | 80 | 80 | 60 |
| 3 Skill | 80 | 100 | 60 | 80 | 80 | 60 |
| 4 MCP/工具 | 100 | 80 | 80 | 80 | 100 | 80 |
| 5 记忆 | 100 | 80 | 60 | 60 | 80 | 80 |
| 6 知识/本体 | 100 | 40 | 20 | 40 | 20 | 20 |
| 7 RAG | 100 | 60 | 40 | 40 | 40 | 20 |
| 8 提示/Cache | 100 | 80 | 60 | 60 | 60 | 80 |
| 9 可观测 | 100 | 40 | 40 | 40 | 60 | 60 |
| 10 质量/幻觉门 | 80 | 40 | 40 | 20 | 40 | 40 |
| 11 自演进 | 80 | 100 | 20 | 40 | 60 | 20 |
| 12 治理 | 100 | 20 | 40 | 40 | 40 | 40 |
| 13 可嵌入 | 80 | 80 | 60 | 80 | 80 | 100 |
| 14 通道/原生端 | 60 | 80 | 40 | 100 | 40 | 40 |
| 15 后端/部署 | 80 | 100 | 40 | 80 | 60 | 60 |
| 16 交付生命周期 | 100 | 40 | 60 | 40 | 40 | 40 |
| 17 OS 沙箱 | 80 | 60 | 80 | 60 | 60 | 100 |
| 18 评测/质量门 | 100 | 40 | 60 | 40 | 60 | 60 |
| **加权总分** | **92** | **70** | **56** | **60** | **62** | **61** |

> 解读：aiPlat 在企业知识/治理/交付上拉开差距；Hermes 在学习与多后端上最强个人 Agent；OpenClaw 通道生态第一；Codex 嵌入与沙箱第一；DSH 插件架构纯度高。分数随证据刷新，**不是**商务承诺。

---

## 四、体系性领先与可借鉴（摘要）

### aiPlat 领先区

1. 企业治理链（Policy/Approval/Audit + 多租户）  
2. 本体/知识引擎与 RAG 治理  
3. 交付流水线 HITL（approve/reject/checkpoint）  
4. 平台级质量门与架构守卫  

### 可借鉴（本轮仍成立）

| 来源 | 能力 | 建议 |
|:---|:---|:---|
| **OpenClaw** | 20+ 通道 + 原生多端 | 企业通道矩阵继续对齐；勿照搬单操作者信任模型到多租户 |
| **Hermes** | 7 终端后端 + 学习闭环 + agentskills.io | 后端插件化、Skill 开放标准兼容评估 |
| **Codex** | app-server / OS 沙箱 / worktree | 加深可嵌入协议与沙箱等价物 |
| **Claude Code** | hooks / checkpoint / plan 产品体验 | 保持 G6 hooks 桥与体验对齐 |
| **DSH** | 插件纯度 / continuation 子代理 | 扩展缝保持，不向「一切皆插件」整仓迁 |

---

## 五、验证

```bash
# 底稿与主报告存在
test -f docs/research/对标底稿-2026-10-五家.md
test -f docs/research/aiPlat核心能力对标报告.md
# 白皮书节选刷新
python3 scripts/generate_whitepaper_volumes.py --check
```

*对标基准日期：2026-10-13 · 权重见第三节 · 旧稿 archive/comparison-four-platform-2026-07.md*


### 3.3 工程落地视图索引（部署 / 性能 / 可观测 / 数据 / 测试 …）

本卷定位是「为什么这样设计」与架构全景；**工程落地细节不在此卷全文复述**，以免形成第二真相源。CTO/架构师做技术尽调时，按下表进入权威源（含物理/部署视图、数据视图、开发视图、质量属性）。

| 工程维度 | 读者要回答的问题 | 权威源（优先） | CAPABILITIES / 姊妹卷 |
|----------|------------------|----------------|----------------------|
| **部署与运维** | 生产怎么布？环境/灾备/灰度？ | [`docs/manuals/deployment.md`](../manuals/deployment.md) · [`docs/architecture/plans/disaster-recovery-plan.md`](../architecture/plans/disaster-recovery-plan.md) · `deploy/helm/aiplat/` | CAPABILITIES「部署与运维 / 部署与灰度」 |
| **性能与扩展** | QPS/P95/容量/扩展策略？ | [`docs/standards/规范-性能.md`](../standards/规范-性能.md) · [`docs/architecture/slo.md`](../architecture/slo.md) · `scripts/benchmark_all.sh` | CAPABILITIES「部署与运维」基准条目 |
| **可观测性** | 日志/指标/追踪怎么采与告警？ | [`docs/architecture/plans/observability-eval-repair-architecture.md`](../architecture/plans/observability-eval-repair-architecture.md) · [`docs/standards/规范-core-run_id-trace_id-request_id.md`](../standards/规范-core-run_id-trace_id-request_id.md) | CAPABILITIES「可观测性」· 安全卷可交叉 |
| **数据架构** | 存什么、隔离、备份？ | [`docs/knowledge-system.md`](../knowledge-system.md) · [`docs/architecture/knowledge-base-architecture.md`](../architecture/knowledge-base-architecture.md) | CAPABILITIES「知识引擎」· 灾备计划（备份） |
| **安全嵌入视图** | Gate/信任边界如何嵌进运行时？ | [`docs/security/security-architecture.md`](../security/security-architecture.md) | 分卷 05 · CAPABILITIES「安全与治理 / Gate」 |
| **测试与验证** | 金字塔 / CI / 质量门？ | [`docs/manuals/testing.md`](../manuals/testing.md) · [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md) · `.github/workflows/` | CAPABILITIES「管理 & 质量」 |
| **技术风险与演进** | 技术债、依赖风险、路线？ | [`AIPLAT_ROADMAP.md`](../../AIPLAT_ROADMAP.md) · [`docs/research/architecture-evolution-roadmap.md`](../research/architecture-evolution-roadmap.md) · [`CLAUDE.md`](../../CLAUDE.md) §16 | 商业卷 ROADMAP 节选（非财务） |
| **开发视图** | 代码组织、模块边界、上手？ | [`CLAUDE.md`](../../CLAUDE.md) · [`docs/DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md) · [`docs/manuals/getting-started.md`](../manuals/getting-started.md) · [`docs/architecture/plans/app-module-layout.md`](../architecture/plans/app-module-layout.md) | — |
| **集成架构** | MCP/A2A/外部适配？ | [`docs/mcp/index.md`](../mcp/index.md) · [`docs/policy/mcp-stdio-prod-allowlist.md`](../policy/mcp-stdio-prod-allowlist.md) | 分卷 04 · CAPABILITIES「MCP / A2A」 |
| **质量属性 / SLA·SLO** | 可用性目标与误差预算？ | [`docs/architecture/slo.md`](../architecture/slo.md) · [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md) | CAPABILITIES「管理 & 质量」 |

> **阅读约定**：上表保证「只读本卷也能知道去哪尽调」。性能容量叙事以规范预算 + `benchmark_all.sh` + SLO 为准；若缺少独立压测报告，以脚本与门禁结果为可执行证据，勿在卷内编造 QPS 数字。

## 4. 相关横切（对标 / 评级）

完整对标与评级目录见总白皮书 §2.5 与 [`docs/whitepaper/WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md)。

## 5. 验证

```bash
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check
```

*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`tech-architecture`*
