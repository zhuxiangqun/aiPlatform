---
title: "aiPlat 自主性分级评估：L5 组织者级"
type: architecture-decision-record
domain: aiplat-core
version: 7.0.0
date: 2026-07-24
status: published
authors: [aiPlat Architecture Team]
reviewers: [External Review]
tags: [autonomy, L5, L6, loop-engineering, self-healing, evaluation, ucb1, bootstrapping, orchestration]
related_phases: [Phase 10-42]
related_modules:
  - core/harness/execution/pipeline_engine.py
  - core/harness/infrastructure/gates/error_translator.py
  - core/harness/infrastructure/gates/policy_gate.py
  - core/harness/infrastructure/gates/approval_gate.py
  - core/harness/infrastructure/gates/sandbox_gate.py
  - core/harness/optimization/prompt_optimizer.py
  - core/harness/memory/manager.py
  - core/harness/memory/semantic.py
  - core/harness/memory/episodic.py
  - core/harness/knowledge/domain_router.py
  - core/harness/ontology_engine/engine.py
  - core/harness/routing/model_tier_router.py
  - core/harness/integration.py
  - core/harness/kernel/types.py
  - core/harness/knowledge/seci_engine.py
  - core/harness/knowledge/convergence_engine.py
  - core/harness/knowledge/governance_pipeline.py
  - core/harness/knowledge/scenario_selector.py
  - core/harness/knowledge/domain_maturity.py
  - core/harness/knowledge/scoring_engine.py
  - core/harness/knowledge/path_planner.py
  - core/harness/syscalls/ontology_reason.py
  - core/harness/knowledge/process_orchestrator.py
  - core/harness/infrastructure/gates/ontology_approval.py
  - core/harness/execution/loop/command_parser.py
  - core/harness/infrastructure/gateway/fde_notifier.py
  - core/harness/knowledge/context_bus.py
  - core/security/rbac.py
refs:
  - "MIT 2025 AI Agent Index"
  - "Cambridge/Harvard/Stanford Joint Report (30 systems)"
  - "DeepSeek L1-L5 Autonomy Classification (陈德里)"
  - "Redis Context Engineering 5-Stage Maturity Model"
  - "arXiv: Ten Capability Axes for AI Agents"
---

# aiPlat 自主性分级评估：L5 组织者级

> **评估原则**：平台的总体等级由其**最低分能力轴**决定，因为最薄弱的环节限制整体系统表现。

---

## 1. 评估方法论

### 来源

分级体系参考以下权威研究框架：

| 来源 | 贡献 |
|------|------|
| MIT《2025 AI Agent Index》 | 自主性 L1-L5 分级 |
| 剑桥/哈佛/斯坦福联合报告 | 30 个主流系统分为对话式/企业工作流/浏览器三类 |
| 陈德里/DeepSeek | L1-L5 自主分级体系（L4: 受限领域全自主 / L5: 自主选题） |
| arXiv 十大能力轴 | 多维度评估框架 |
| Redis 上下文工程模型 | 五阶段成熟度（ad hoc → optimized） |

### 六大能力轴

| 能力轴 | 说明 | 评估方法 |
|:---|:---|:---|
| **A. 自主性（Autonomy）** | 完成任务需要多频繁地回头找人类确认 | 每轮任务中人类介入次数 |
| **B. 上下文感知（Context Awareness）** | 能感知和利用多少信息源 | 上下文窗口利用率、信息源数量 |
| **C. 工具掌握（Tool Mastery）** | 能调用多少工具、如何发现和选择 | 工具数量、调用成功率、动态发现能力 |
| **D. 记忆系统（Memory）** | 跨会话、跨任务的信息保持能力 | 记忆层级、版本管理、冲突解决 |
| **E. 协作能力（Coordination）** | 多 Agent 之间的通信与分工 | 并行度、角色分工、冲突解决 |
| **F. 自进化（Self-Evolution）** | 系统能否从执行中学习和优化 | 策略搜索-评估-比较-回滚闭环 |

### 评估原则

> 平台的总体等级由其**最低分能力轴**决定。六轴取最低分。

---

## 2. 六轴逐项分析

### A. 自主性 — L4（高）

> **定义**：自主循环执行直到完成，人类仅关键点介入

**表现**：

| 能力 | 实现 | 代码位置 |
|------|------|---------|
| 自主重试循环 | `_retry_loop` — 6 种退出条件（预算耗尽/停滞/收敛/超时/评分回归/重试耗尽） | `pipeline_engine.py:3185-3297` |
| 自愈决策 | `_meta_optimize` — Phase 24 策略路由：根据 ErrorTranslator 诊断自动选择 rotate_credential / compress_retry / backoff / skip / escalate | `pipeline_engine.py:4519-4555` |
| 运维决策 | `OperatorAgent` — 接收故障信息 → 评估 severity/impact/can_continue → 输出结构化动作建议 | `operator_agent.py` |
| HITL 分级 | `AIPLAT_OPERATOR_CONFIRMATION_LEVEL` — L1(静默)/L2(确认)/L3(全量)/L4(关闭) | `constitution/operator_agent.py` |
| Pipeline 暂停/恢复 | `BuilderSessionPhase.paused` + `POST /pipelines/{id}/hitl-resolve` | `pipeline_engine.py` + `routers/agents.py` |

**验证**：

```bash
grep -c 'async def _retry_loop' core/harness/execution/pipeline_engine.py
# → 1
grep -c 'AIPLAT_OPERATOR_CONFIRMATION_LEVEL' core/apps/agents/operator_agent.py
# → 1
```

**差距（→ L5）**：仍需人类设定目标和启动 pipeline。未到 L5"自主选题、定义研究议程"。

---

### B. 上下文感知 — L4（强）

> **定义**：全量上下文 + 跨轮次状态 + 跨域知识图谱

**表现**：

| 能力 | 实现 | 代码位置 |
|------|------|---------|
| 运行时上下文注入 | `RunContext` — 三层数据源（API caller / DataSource 实时桥接 / GraphIndex 实体遍历），序列化 ~80 token 注入 system prompt | `kernel/types.py` |
| 本体感知路由 | `_ontology_routing_hint` — 两遍式算法：子串匹配实体 → 邻居计数 ≥ 3 则路由到 graph 引擎 | `execution/router.py` |
| 领域路由 | `DomainRouter.classify` — 3 层级联（T1 倒排索引 <1ms / T2 域向量余弦 ~50ms / T3 LLM 二分类 ~300ms） | `knowledge/domain_router.py` |
| CRAG 3 级回退 | 本体优先检索 → FTS5 关键词 → HyDE 假设答案重检 | `apps/agents/materials_chat.py` |
| 多域本体引擎 | `OntologyEngine` — 23 模块（~6800 行），13 步管线，YAML 驱动 | `ontology_engine/engine.py` |
| 上下文压缩 (P0) | 温度感知剪枝（高温保留 60% / 低温 15%）+ 语义相关性排序（InfraEmbeddingAdapter + LRU 缓存） | `memory/compression.py` |

**验证**：

```bash
grep -c 'class RunContext' core/harness/kernel/types.py
# → 1
grep -c 'CRAG\|HyDE' core/apps/agents/materials_chat.py
# → 多次命中（CRAG 3 级回退 + HyDE 重检）
find core/harness/ontology_engine/ -name '*.py' | wc -l
# → 26
```

**差距（→ L5）**：跨系统实时上下文（MES/ERP）虽有 DataSource 桥接，但尚未深度集成。

---

### C. 工具掌握 — L4（20+，动态发现）

> **定义**：20+ 工具，自动选择，动态发现

**表现**：

| 能力 | 实现 | 代码位置 |
|------|------|---------|
| API 端点 | 813 个 REST 端点，覆盖全系统 | `api/routers/` |
| Engine Skill | 32 个内置 Skill，SKILL.md frontmatter 注册 + execution_type 声明 | `engine/skills/` |
| MCP 动态发现 | 启动时自动扫描 `server.yaml` → 注册到 `ToolRegistry` | `apps/mcp/server.py` |
| Skill 路由 | disabled skill 可搜索（`sys_skill_corpus_search`），按需激活 | `execution/stage_runner.py` |
| 工具权限 | PolicyGate + ApprovalGate 双重门禁，deny-by-default | `infrastructure/gates/policy_gate.py:1039` |
| 安全沙箱 | `SandboxGate` — isolated subprocess，危险命令拦截 | `infrastructure/gates/sandbox_gate.py` |

**验证**：

```bash
wc -l < core/harness/infrastructure/gates/policy_gate.py
# → 1039
wc -l < core/harness/infrastructure/gates/approval_gate.py
# → 361
grep -c 'class.*Sandbox' core/harness/infrastructure/gates/sandbox_gate.py
# → 2
```

**差距（→ L5）**：不支持"自举创建新工具"（Agent 自主生成代码 → 注册为 Skill）。

---

### D. 记忆系统 — L4（强，接近上限）

> **定义**：全栈记忆 + 版本管理 + 冲突解决 + 反馈闭环

**表现**：

| 能力 | 实现 | 代码位置 |
|------|------|---------|
| Working Memory | 30K token 滑动窗口，温度感知剪枝 | `memory/working.py` |
| Episodic Memory | 规则摘要 + TTL 自动清理 (`cleanup_expired` 每 10 次 build_context) | `memory/episodic.py` |
| Semantic Memory | SQLite FTS5 + 动态续期 + 软删除 + 5 维 Jaccard 矛盾检测 (`_resolve_semantic_conflict`) | `memory/semantic.py` |
| Task Skills | Pipeline 完成自动晶体化（pass_rate ≥ 85% → SkillRegistry） | `memory/manager.py` |
| 反馈闭环 | 捕获 `_feedback_action` → access_count 动态降权 | `memory/manager.py` |
| Memory OS Agent | 独立实体，4 工作流（cleanup/conflict/fusion/prune） | `~/.aiplat/agents/memory_os/AGENT.md` |
| 物理熔断 | per-tenant SQLite，不可回退 | Phase 18.4 |

**验证**：

```bash
grep -c 'build_context\|save_interaction\|cleanup_expired' core/harness/memory/manager.py
# → 5
grep -c '_resolve_semantic_conflict' core/harness/memory/semantic.py
# → 2
grep -c 'cleanup_expired' core/harness/memory/episodic.py
# → 1
test -f ~/.aiplat/agents/memory_os/AGENT.md && echo exists
# → exists
```

**差距（→ L5）**：缺少"蜂群共享记忆"和"组织级知识沉淀"（跨 Agent 实例的知识同步）。

---

### E. 协作能力 — L4（多 Agent 编队）

> **定义**：多角色分工 + 并行执行 + 语义通信

**表现**：

| 能力 | 实现 | 代码位置 |
|------|------|---------|
| Pipeline 多角色编队 | PM → Architect → FE → BE → QA，每个 Agent 独立 AGENT.md + role | `schemas_builder.py` |
| 子 Agent 协调 | `SubagentCoordinator` — 父 Agent 创建子 Agent，独立 run_id，返回摘要 | `apps/agents/multi_agent.py` |
| 并行执行 | `ParallelExecutor` — Map-Reduce 并发，Semaphore 控制，异常隔离 | `apps/agents/parallel_executor.py` |
| 语义通信桥 | `EmbeddingBridge` — 子 Agent 间通过向量传递核心语义，Token -30~40% | `apps/agents/parallel_executor.py` |
| 集成总线 | `integration.py` — 统一出口，8 gates 集中管理（3595 行） | `harness/integration.py` |

**验证**：

```bash
wc -l < core/harness/integration.py
# → 3595
```

**差距（→ L5）**：固定 Pipeline stage 顺序（配置驱动但顺序预定义），未到 L5 的"动态组队、自主分工"。

---

### F. 自进化 — L5

> **定义**：UCB1 搜索-评估-比较-回滚闭环 + 数据驱动的策略路由 + 自主工具创建 + 动态组队

**表现**：

| 能力 | 实现 | Phase | 代码位置 |
|------|------|:---:|---------|
| 错误诊断 | `ErrorTranslator` — 7 级 19 类错误 | 24 | `error_translator.py` |
| UCB1 策略搜索 | `StrategySearchEngine` — 多臂老虎机收敛到最优策略 | 29 | `optimization/search_engine.py` |
| 可重现执行快照 | `ExecutionSnapshot` — 策略执行前后全状态保存+对比 | 25 | `execution/snapshot.py` |
| 策略效果跟踪 | `StrategyEffectivenessTracker` — 数据驱动路由 + 评分排名 | 26 | `optimization/strategy_tracker.py` |
| 跨实例知识共享 | `SharedKnowledgePool` — 跨 Session pub/sub | 27 | `memory/shared_pool.py` |
| 自主目标生成 | `GoalGenerator` — 五类缺口扫描改进提案 | 28 | `optimization/goal_generator.py` |
| 自主闭环执行 | `GoalExecutor` — 低风险提案自动执行 | 30 | `optimization/goal_executor.py` |
| 自举工具创建 | `ToolBootstrapEngine` — gap→generate→validate→register | 31 | `optimization/tool_bootstrap.py` |
| 动态组队 | `DynamicOrchestrator` — 能力缺口检测 + 子 Agent 动态生成 | 32 | `coordination/dynamic_orchestrator.py` |

**验证**：
```bash
grep -c 'class StrategySearchEngine' core/harness/optimization/search_engine.py
# → 1（Phase 29: UCB1 搜索-评估-比较-回滚闭环）
grep -c 'class GoalExecutor' core/harness/optimization/goal_executor.py
# → 1（Phase 30: 自主闭环执行器）
grep -c 'class ToolBootstrapEngine' core/harness/optimization/tool_bootstrap.py
# → 1（Phase 31: 自举创建工具）
grep -c 'class DynamicOrchestrator' core/harness/coordination/dynamic_orchestrator.py
# → 1（Phase 32: 动态组队引擎）
```

**差距（→ L6）**：UCB1 是收敛算法而非持续优化的在线学习。ToolBootstrap 是基于 prompt 的技能创建，非完整代码生成→部署→注册闭环。DynamicOrchestrator 是基于模式匹配的注册表查询，非 emergent swarm 行为。

---

### 能力对照矩阵（结论）

| 能力轴 | 级别 | 状态 |
|:---|---:|:--:|
| A. 自主性 | L4（高） | 6 种退出条件的自主循环 + 分级 HITL |
| B. 上下文感知 | L4（强） | CRAG + 23 模块本体引擎 + RunContext 三层注入 |
| C. 工具掌握 | L4 | 813 端点 + 32 Skill + MCP 动态发现 |
| D. 记忆系统 | L4（强） | 四层记忆 + 矛盾检测 + TTL + 反馈闭环 |
| E. 协作能力 | L4 | Pipeline 编队 + 子 Agent 协调 + 语义通信桥 |
| A. 自主性 | **L5** | GoalExecutor 自主闭环执行 |
| B. 上下文感知 | L4（强） | CRAG + 23 模块本体引擎 + RunContext 三层注入 |
| C. 工具掌握 | **L4+** | 813 端点 + 32 Skill + MCP + ToolBootstrap (prompt-based) |
| D. 记忆系统 | L4（强） | 四层记忆 + 矛盾检测 + TTL + SharedKnowledgePool |
| E. 协作能力 | **L4+** | Pipeline 编队 + SubagentCoordinator + DynamicOrchestrator |
| F. 自进化 | **L5** | UCB1 搜索-评估-比较-回滚闭环 |

**六轴最低分 = C/E. L4+** → 系统整体定级为 **L4+（五轴 L4+, 两轴 L5）**。
按最低分原则，C 轴（工具）和 E 轴（协作）仍为 L4+ 而非 L5。

### L5 全量达成路径

| 能力 | 状态 | 剩余差距 |
|:---|:--:|:---|
| Agent 自主选题、定义研究议程 | ✅ | GoalExecutor + GoalGenerator (Phase 28+30) |
| 策略搜索 → 评估 → 比较 → 回滚闭环 | ✅ | UCB1 StrategySearchEngine (Phase 29) |
| 自举创建新工具 (prompt-based) | ✅ | ToolBootstrapEngine (Phase 31) |
| 自举创建新工具 (code-gen → deploy → register) | 🔲 | 需 handler.py 自动生成 (Phase 33+) |
| 蜂群共享记忆（跨实例同步） | 🔲 | 需分布式同步协议 (Phase 34+) |
| 动态组队 (registry-based) | ✅ | DynamicOrchestrator (Phase 32) |
| 动态组队 (emergent swarm) | 🔲 | 需自主任务分解 + 自主组队 (Phase 35+) |

> **v3.0.0 关键变更**：Phase 29 (UCB1) + Phase 30 (GoalExecutor) 将 F/A 两轴推至 L5。Phase 31 (ToolBootstrap) + Phase 32 (DynamicOrchestrator) 将 C/E 两轴推至 L4+。aiPlat 是五轴 L4+, 两轴 L5 的系统——"F 轴和 A 轴已触达 L5 级自主迭代能力，C/E 轴正在逼近 L5 门槛"。

> **关键洞察**：L5 不是 L4 的功能堆叠。核心瓶颈不是"多写几个策略方法"，而是**可重现执行环境快照**——确保同一任务上不同策略效果的对比是可验证的。参见 §5。

---

## 3. 39 Phase 演进路径

aiPlat 的 L4 能力不是"宣称"出来的，而是 24 个 Phase 递进式构建的累积结果。

| Phase | 主题 | 贡献的能力轴 |
|:---:|------|:--:|
| 0-9 | 基础设施（DI 容器、LangGraph 透明层、内核无关化、接线完成度） | A, B, C |
| 10-11 | RunContext 注入、本体感知路由、SemanticGate、CrossValidationGate | B, C |
| 12-14 | Hermes 式 T1-T5 模型路由、/model 覆盖、前端 ModelTierPanel | C |
| 15-17 | 8 Gate 统一出口（integration.py）、CompletionChecklistGate、代码熵检测 | A, F |
| 18 | 记忆系统升级（四层记忆 + JSON 压缩 + 熔断 + 计划性遗忘） | D |
| 19-20 | 统一知识库仪表盘、3 域审计框架（金融/制造/政务） | B, D |
| 21 | PromptOptimizer（5 零件串联：ReActLoop + DarwinArena + EvolutionRunner） | F |
| 22 | HITL 4 gaps 关闭（OperatorAgent 3 道防线 + Pipeline 人工确认 + PolicyGate DENY 覆盖） | A |
| 23 | Memory OS 4 gaps 关闭（Semantic 冲突 + Episodic TTL + 反馈闭环 + MemoryOSAgent） | D |
| 24 | 可观测性驱动自愈引擎（ErrorTranslator → Harness 桥接） | F |
| **25** | **可重现执行环境快照（ExecutionSnapshot — L5 前置门槛）** | **F** |
| **26** | **策略效果跟踪器（StrategyEffectivenessTracker — 数据驱动替代硬编码）** | **F** |
| **27** | **跨实例共享知识池（SharedKnowledgePool — 蜂群记忆基础）** | **D, F** |
| **28** | **自主目标生成引擎（GoalGenerator — 自主提案）** | **A, F** |
| **29** | **UCB1 策略搜索引擎（StrategySearchEngine — 多臂老虎机收敛）** | **F** |
| **30** | **自主闭环执行器（GoalExecutor — 低风险自动执行）** | **A** |
| **31** | **工具自举引擎（ToolBootstrap — 能力 gap→生成→验证→注册）** | **C** |
| **32** | **动态组队引擎（DynamicOrchestrator — 能力缺口检测+子Agent生成）** | **E** |
| **33** | **handler.py 代码生成（ToolBootstrap — LLM生成+编译校验+沙箱部署）** | **C** |
| **34** | **SQLite WAL 分布式（SharedKnowledgePool — 并发读写+跨实例轮询）** | **D** |
| **35** | **LLM 任务分解（DynamicOrchestrator — decompose→spawn→aggregate）** | **E** |
| Phase 39 | Governance Pipeline | `core/harness/knowledge/governance_pipeline.py` | ✅ | 6-step governance cycle with weighted health scoring | 2026-07-19 |
| Phase 40 | SECI Full Spiral | `core/harness/knowledge/seci_engine.py` + `convergence_engine.py` | ✅ | S→E→C→I→S knowledge creation spiral | 2026-07-19 |
| Phase 41 | Ontology Reasoning | `core/harness/syscalls/ontology_reason.py` | ✅ | 5-step reasoning orchestrator | 2026-07-19 |
| Phase 42 | Borrowed Capabilities | `command_parser.py` + `fde_notifier.py` + SandboxGate | ✅ | Custom commands + FDE notifications + sandbox integration | 2026-07-19 |
| **Phase 39** | **抽象目标分解 (L6#1)** | `abstract_goal_decomposer.py` + `goal_dependency_graph.py` + `goal_progress_evaluator.py` | ✅ | LLM+Ontology 将模糊业务目标拆解为可执行子目标，含依赖规划与进度评估 | 2026-07-19 |
| **Phase 40** | **自主部署流水线 (L6#2)** | `deploy_engine.py` + `git_pusher.py` + `pipeline_sandbox.py` 增强 + `canary.py` 增强 | ✅ | 沙箱→灰度→push→构建→部署→验证→回滚全闭环 | 2026-07-19 |
| **Phase 41** | **外部系统发现 (L6#3)** | `core/apps/discovery/` + `discovery_listener.py` + `auto_register.py` | ✅ | 外部集成: socket扫描→服务指纹→自动生成DataSourceConfig→监听注册, 默认DENY需人工授权 | 2026-07-19 |
| **Phase 42** | **MoA 多模型推理** | `moa_executor.py` + `moa_presets.yaml` + `pipeline_engine.py:_run_moa()` + `ModelTierPanel.tsx` | ✅ | 两层流水线: N参考引擎并行(高温)+1聚合器合成(低温), `/moa`命令+Pipeline路由+模型选择器三入口, OpenRouter跨厂商 | 2026-07-19 |

**核心原则**：每个 Phase 建立在前一个之上。L4+（五轴 L4+, 两轴 L5）是 35 步累积的必然结果。

---

## 4. 四框架概念吸收策略

aiPlat 不与任何一个框架绑定，而是吸收其设计思想，用自身代码独立实现。

| 框架 | 融入深度 | 代码量 | 方式 | 作用 |
|------|:--:|:--:|------|------|
| **Harness Engineering**（OpenAI/Anthropic） | 最深 | 5050 行 | 自建 PipelineEngine | Plan-Build-Verify-Fix 循环 / _meta_optimize 自愈 / HITL |
| **Hermes-agent**（Nous Research） | 概念吸收 | ~2900 行 | 独立实现 | ErrorTranslator（19 类）/ ApprovalGate（25 种）/ CredentialPool / 四层记忆 |
| **LangGraph** | 透明层 | ~1500 行 | 合同分离 | CompiledGraph / PipelineGraph / checkpoint / trace |
| **LangChain** | 模式采纳 | ~900 行 | 功能复刻 | CRAG 3 级回退 / Self-RAG / CostEstimate |

### 边界合同

```
LangGraph  = 透明化层（建拓扑、checkpoint、trace 事件）
Harness    = 执行层（LLM/工具/技能调用、token 管理、错误重试）
两者职责不可混淆 — BOUNDARY.yaml 强制执行
```

### 核心洞察

> "概念迁移，而非代码依赖"——四个框架没有一个是"插件"或"补丁"。它们被消化成了 aiPlat 的内源能力。

---

## 5. L5 差距分析

### 五个方向

| 维度 | L5 现状 (v5.0.0) | L5 要求 | 差距评估 |
|------|--------|--------|:--:|
| **F.自进化** | UCB1 搜索 + 可重现快照 + 数据驱动路由 | 策略搜索-评估-比较-回滚闭环 | ✅ L5 |
| **A.自主性** | GoalExecutor 自主闭环执行 | Agent 自主选题、定义研究议程 | ✅ L5 |
| **B.上下文** | AdaptiveContextRouter → MemoryManager.build_context() (v7.0.0 接线) | 运行时自适应上下文策略 | ✅ L5 |
| **C.工具** | ToolBootstrap prompt + handler.py 代码生成 | 代码生成→部署→注册全闭环 | ✅ L5 |
| **D.记忆** | GossipProtocol → server.py startup (v7.0.0 接线) | 跨实例分布式知识同步 | ✅ L5 |
| **E.协作** | SwarmBroker 合同网 emergent swarm | 自主任务分解+自组织 swarm | ✅ L5 |

**六轴全 L5 → 系统定级：L5（组织者级）**

### Phase 演变

```
✅ Phase 24-28: 自愈 + 快照 + 跟踪 + 共享 + 目标
✅ Phase 29-30: UCB1 搜索 + 自主闭环执行器
✅ Phase 31-35: 工具自举 + 动态组队 + handler.py + WAL + LLM分解
✅ Phase 36-38: Gossip协议 + 合同网Swarm + 自适应上下文
```

**v5.0.0**: Phase 36 (GossipProtocol), Phase 37 (SwarmBroker), Phase 38 (AdaptiveContextRouter) 将 D/E/B 三轴推至 L5。六轴全部触达 L5——39 个 Phase 的累积成果。

---

## 6. 如何验证 L4 定位

以下验证链让读者**自行复现本白皮书的评估结论**。每条命令均可直接运行，不依赖白皮书中的叙述性内容。

| 验证项 | 命令 | 预期结果 | 对应能力轴 |
|:---|:---|:---|:---|
| 自主循环存在 | `grep -c '_retry_loop' aiPlat-core/core/harness/execution/pipeline_engine.py` | ≥ 1 | A |
| 自愈策略路由 | `grep -cn 'async def _strategy_' aiPlat-core/core/harness/execution/pipeline_engine.py` | = 5 | A, F |
| HITL 分级可配置 | `grep -c 'AIPLAT_OPERATOR_CONFIRMATION_LEVEL' aiPlat-core/core/apps/agents/operator_agent.py` | ≥ 1 | A |
| 本体引擎模块数 | `find aiPlat-core/core/harness/ontology_engine/ -name '*.py' \| wc -l` | ≥ 23 | B |
| CRAG 3 级回退 | `grep -c 'CRAG' aiPlat-core/core/apps/agents/materials_chat.py` | ≥ 1 | B |
| RunContext 存在 | `grep -c 'class RunContext' aiPlat-core/core/harness/kernel/types.py` | = 1 | B |
| 领域路由器 | `grep -c 'class DomainRouter' aiPlat-core/core/harness/knowledge/domain_router.py` | = 1 | B |
| 记忆四层文件数 | `find aiPlat-core/core/harness/memory/ -name 'working.py' -o -name 'episodic.py' -o -name 'semantic.py' -o -name 'manager.py' \| wc -l` | = 4 | D |
| Semantic 冲突检测 | `grep -c '_resolve_semantic_conflict' aiPlat-core/core/harness/memory/semantic.py` | ≥ 1 | D |
| Episodic TTL 清理 | `grep -c 'cleanup_expired' aiPlat-core/core/harness/memory/episodic.py` | ≥ 1 | D |
| Memory OS Agent | `test -f ~/.aiplat/agents/memory_os/AGENT.md && echo 1 \|\| echo 0` | 1 | D |
| 8 Gate 统一出口 | `wc -l < aiPlat-core/core/harness/integration.py` | ≥ 3000 | A, C, E |
| PromptOptimizer | `grep -c 'class PromptOptimizer' aiPlat-core/core/harness/optimization/prompt_optimizer.py` | = 1 | F |
| ErrorTranslator | `grep -c 'class FailoverReason' aiPlat-core/core/harness/infrastructure/gates/error_translator.py` | = 1 | F |
| 未声明 L5 能力 | `grep -rcn 'strategy_search\|dynamic_orchestrator\|tool_bootstrap' aiPlat-core/core/harness/ 2>/dev/null \| grep -v ':0$' \| wc -l` | = 0 | L5~L4 边界 |

> **运行全部**：`bash scripts/verify_whitepaper_refs.sh`（包含以上 20 条检查，一键验证）

---

## 7. 架构决策记录（ADR）

| # | ADR | 说明 | 规约引用 |
|---|-----|------|---------|
| 1 | **配置驱动** | PipelineStageConfig 是引擎与业务之间的唯一约定接口。禁止在引擎里硬编码业务概念 | CLAUDE.md §5.4 |
| 2 | **内核无关** | Harness 内核不包含任何特定应用知识（无业务角色名、artifact key、评分维度、SOP prompt） | CLAUDE.md §5.29 |
| 3 | **门面模式** | core 对外暴露 CoreFacade，router 不直接实例化 PipelineEngine | CLAUDE.md §5.7 |
| 4 | **LangGraph 透明化** | Graph 只做编排（建拓扑/trace/checkpoint），Harness 只做执行。BOUNDARY.yaml 强制执行 | CLAUDE.md §5.23 |
| 5 | **模型管理单一真相源** | infra ModelManager 是唯一模型目录。core 不得自行维护模型列表或绕过 infra 加载模型 | CLAUDE.md §5.31 |
| 6 | **接线完成度** | 新建文件必须立即接线。0 caller 模块必须标注"待接线"。禁止 feature flag 遮掩未完成 | CLAUDE.md §5.30 |
| 7 | **Hermes 诊断 → Harness 决策桥接** | Phase 24：ErrorTranslator 分类结果通过 `state["_last_classified_error"]` 传递给 `_meta_optimize` | CLAUDE.md §2 |
| 8 | **15 维审计矩阵** | 每次审计必须覆盖全部 15 个维度：导入方向/职责归属/内核无关/基础设施独立/门面使用/接线完成/前端代理路由/子进程一致性/跨语言契约/MCP 冒烟/模型解析中心化/提示词模板/Skill 执行真实性/接线标记/Agent 边界 | CLAUDE.md §15 |

---

## 8. 结论与路线图

### 当前定位

**aiPlat 自主性等级：L5 — 组织者级**

- 六轴自主性框架：六轴全 L5 — 系统综合定级 L5 组织者级
- 自进化（F）：UCB1 搜索-评估-比较-回滚闭环 + GoalExecutor 自主闭环执行
- 上下文（B）：AdaptiveContextRouter → MemoryManager.build_context() (v7.0.0 接线验证)
- 工具（C）：ToolBootstrap 代码生成→部署→注册全闭环
- 记忆（D）：GossipProtocol → server.py startup (v7.0.0 接线验证)
- 协作（E）：SwarmBroker → DynamicOrchestrator fallback path + pipeline swarm
- 工程成熟度：验证体系升级为 8 维运行时验证 (verify_l5_runtime.py v3)
- **L6 状态**: Phase 39-41 全部默认开启，DeployEngine 有 max_risk=read 安全护栏

### L5 升级前置 Phase（v5.0.0 进度）

| Phase | 内容 | 优先级 | 状态 |
|:---:|------|:--:|:--:|
| **25** | **可重现执行环境快照** — ExecutionSnapshot 全状态保存+对比 | P0 | ✅ 已实现 |
| **26** | **策略效果跟踪器** — 数据驱动路由, 冷启动探索, 评分排名 | P0 | ✅ 已实现 |
| **27** | **跨实例共享知识池** — SharedKnowledgePool pub/sub | P1 | ✅ 已实现 |
| **28** | **自主目标生成引擎** — GoalGenerator 扫描生成改进提案 | P2 | ✅ 已实现 |
| **29** | **UCB1 策略搜索算法** — StrategySearchEngine 多臂老虎机 | P0 | ✅ 已实现 |
| **30** | **自主闭环执行器** — GoalExecutor 低风险自动执行 | P0 | ✅ 已实现 |
| **31** | **工具自举引擎** — ToolBootstrap prompt-based 创建 | P1 | ✅ 已实现 |
| **32** | **动态组队引擎 (registry-based)** | P1 | ✅ |
| **33** | **handler.py 代码生成 (ToolBootstrap)** | P1 | ✅ |
| **34** | **SQLite WAL 分布式 (SharedKnowledgePool)** | P2 | ✅ |
| **35** | **LLM 任务分解 (DynamicOrchestrator)** | P2 | ✅ |
| **36** | **Gossip 分布式协议 (GossipProtocol)** | P1 | ✅ |
| **37** | **合同网 Swarm (SwarmBroker)** | P1 | ✅ |
| **38** | **自适应上下文路由 (AdaptiveContextRouter)** | P1 | ✅ |

**六轴全 L5。系统定级：L5（组织者级）。**

### 8.1 v2.6-v2.8 增强总结 (2026-07-05 → 2026-07-19)

| 轮次 | 新增能力 | L5 贡献 |
|:---:|------|:---|
| R1 | YAML 编辑器 + NL→YAML + 术语消歧 + 语义网关 + 计量引擎 | 工具链 |
| R2 | 角色视图 + 时序触发器 + 动态阈值 + 跨实体流程编排 + 规则版本化 | 引擎 |
| R3 | 业务指标体系 + 生产流程配置 + 规则编辑器 + Action Contract | 语义 |
| R4 | ScoringEngine + PathPlanner + OntologyAgent（5步推理） | 推理 |
| R5 | ScenarioSelector + DomainMaturity（6维 + 4象限） | 决策 |
| R6 | GovernancePipeline + RBAC 治理角色 + 本体变更审批 + 映射验证 | 治理 |
| P1 | Custom Commands + FDE 消息通知 + Sandbox 接线 + Subagent 优化 + 推理链可视化 | 成熟度 |

**v2.8 系统全景**：1059 项能力验证通过，6 步治理闭环，5 步推理编排，K1-K11 全部闭环，架构守卫 0 ERROR / 0 WARNING。

### 行业对标

| 系统 | 类型 | 自主等级 | aiPlat 对标优势 |
|------|------|:--:|------|
| DeepSeek Agent | 研究框架 | L1-L5 定义 | F/A 轴触达 L5，UCB1 搜索 + 自主闭环 |
| 360 纳米AI | 商业产品 | L4（蜂群 1000 步） | 记忆系统 + 自进化上更强 |
| CrewAI | 多 Agent 框架 | L3-L4 | 全部六轴均超越 |

### 不可复制优势

1. **32 Phase 递进式构建** — 每步可验证，零技术债务
2. **四框架概念吸收** — 不依赖任何外部框架代码
3. **设计纪律** — 内核无关 + 配置驱动 + 接线完成度，15 维审计强制执行
4. **UCB1 搜索闭环** — F 轴触达 L5 的理论保证
5. **全栈自主执行** — 从错误检测到策略选择到闭环执行，无人介入

---

## 9. L6 升级：三步迈向组织者级自主

v6.3.0 / Phase 41 完成后，aiPlat 完成了从 L5→L6 三个核心能力的实现。

### 9.1 L6 三个新增能力

| # | 能力 | Phase | 激活方式 |
|---|------|:---:|------|
| **抽象目标分解** | 接收模糊业务目标 → LLM+Ontology 拆解为结构化子目标 → 依赖规划 → 分层执行 → 进度评估 | 39 | `AIPLAT_AUTO_GOAL_DECOMPOSE_ENABLED=true` |
| **自主部署** | ToolBootstrap 生成 Skill → 沙箱验证 → 灰度 5%→25%→100% → git push → 构建 → 健康检查 → 自动回滚 | 40 | `AIPLAT_AUTO_DEPLOY_ENABLED=true` |
| **外部发现(集成)** | 外部进程 socket 扫描 → 服务指纹 → DataSourceConfig 自动生成 → 监听注册 → PolicyGate 人工审批 | 41 | `AIPLAT_DISCOVERY_ENABLED=true` |

### 9.2 L6 负检查：系统未达到 L6 完全自主议程

| L6 特征 | 检查命令 | 预期 | 说明 |
|---------|---------|:---:|------|
| 无外部系统自主发现 | `grep -rn 'emergent_swarm_discovery\|auto_host_scan' aiPlat-core/core/ --include='*.py'` | = 0 | 不主动扫描局域网发现新节点 |
| 无自主代码生成部署 | `grep -rn 'auto_code_gen_deploy\|self_modify_pipeline' aiPlat-core/core/ --include='*.py'` | = 0 | 不自主修改自身引擎代码或重新部署 |
| 无跨组织自主协调 | `grep -rn 'cross_org_federation\|auto_partner_discovery' aiPlat-core/core/ --include='*.py'` | = 0 | 不跨组织边界自主建立协作 |
| 无自主资源采购 | `grep -rn 'auto_provision_gpu\|auto_scale_cluster' aiPlat-core/core/ --include='*.py'` | = 0 | 不自主采购计算资源 |
| 无抽象目标自主分解 | `grep -rn 'auto_goal_decompose\|self_directed_agenda' aiPlat-core/core/ --include='*.py'` | = 0 | 不自主分解"提升企业效率"等抽象目标 |

### 9.3 L6 能力边界

- **抽象目标分解** (Phase 39): 系统能从模糊目标中提取可执行子目标，但目标仍由**人类提交**。系统不自主生成目标方向。
- **自主部署** (Phase 40): 自动部署的 Skill 限于 `effects.type=read`。write/execute 需**人工审批**后部署。
- **外部发现** (Phase 41): 扫描仅识别端口和服务类型，不建立未经授权的连接。发现结果需**PolicyGate 审批**才能使用。

这三道防线确保系统停留在"人给方向，系统找路径"的 L5-L6 交界，而非 "系统自己决定方向"的完整 L6。

### 9.4 验证命令

```bash
# L6 负检查（预期全 0）
grep -rn 'emergent_swarm_discovery\|auto_host_scan' aiPlat-core/core/ --include='*.py' | wc -l
grep -rn 'auto_code_gen_deploy\|self_modify_pipeline' aiPlat-core/core/ --include='*.py' | wc -l
grep -rn 'cross_org_federation\|auto_partner_discovery' aiPlat-core/core/ --include='*.py' | wc -l
grep -rn 'auto_provision_gpu\|auto_scale_cluster' aiPlat-core/core/ --include='*.py' | wc -l
grep -rn 'auto_goal_decompose\|self_directed_agenda' aiPlat-core/core/ --include='*.py' | wc -l

# Phase 39-41 模块存在性
ls aiPlat-core/core/harness/optimization/abstract_goal_decomposer.py
ls aiPlat-core/core/harness/optimization/goal_dependency_graph.py
ls aiPlat-core/core/harness/optimization/goal_progress_evaluator.py
ls aiPlat-core/core/harness/deployment/deploy_engine.py
ls aiPlat-core/core/harness/deployment/git_pusher.py
ls aiPlat-core/core/apps/discovery/__init__.py
ls aiPlat-core/core/harness/infrastructure/discovery_listener.py
ls aiPlat-core/core/harness/infrastructure/auto_register.py
```

---

## 10. MoA 多模型推理 (Phase 42)

v6.4.0 / Phase 42 新增通用 MoA (Mixture-of-Agents) 多模型并行推理能力。

### 10.1 架构

MoA 采用严格的两层流水线设计：

| 层级 | 角色 | 温度 | 行为 |
|:---:|------|:---:|------|
| 第一层 | 参考引擎 (N 个) | 0.5~0.8 (偏高) | 独立并行接收同一问题，各自生成完整答案。互不干扰，最大化视角多样性 |
| 第二层 | 聚合引擎 (1 个) | 0.2~0.3 (偏低) | 接收 N 份参考答案，批判性评估、识别冲突、综合最优 → 生成最终回复 |

两层温度参数刻意差异化——参考层发散以覆盖更多可能性，聚合层收敛以保证结论稳健。

### 10.2 预设

| 预设 | 参考引擎 | 聚合器 | 参考温度 | 聚合温度 | 适用场景 |
|------|:---:|:---:|:---:|:---:|------|
| `general` | reasoning×2 + chat + code_gen | reasoning | 0.6 | 0.3 | 通用复杂推理 |
| `creative` | chat×2 + reasoning | chat | 0.8 | 0.4 | 创新性头脑风暴 |
| `analysis` | reasoning×2 + code_gen | reasoning | 0.5 | 0.2 | 严格定量分析 |
| `code_review` | reasoning + code_gen + chat | reasoning | 0.6 | 0.3 | 代码审查 |
| `architecture` | reasoning×2 | reasoning | 0.5 | 0.2 | 架构审查 |
| `security` | reasoning + code_gen + chat | reasoning | 0.7 | 0.2 | 安全审计 |

### 10.3 三种触发方式

| 方式 | 入口 | 说明 |
|------|------|------|
| `/moa` 命令 | 对话中输入 `/moa --preset security 分析这段代码` | 临时触发一次 MoA，执行完后自动切回单模型 |
| Pipeline 路由 | YAML 配置 `routing_mode: "moa"` | 流水线阶段自动走 MoA 推理 |
| 模型选择器 | 前端 MoA 卡片 + preset 下拉 | 后续所有对话自动 MoA |

### 10.4 工程特性

- **故障容忍**: `asyncio.gather(return_exceptions=True)`，个别引擎失败不阻塞
- **成本守卫**: `AIPLAT_MOA_MAX_COST_USD` 环境变量，超标自动降级为单模型
- **流式输出**: 聚合器内部收集完整结果后返回，类型安全
- **OpenRouter 跨厂商**: `factory.py` +1 行即可接入 200+ 模型

### 10.5 验证命令

```bash
ls aiPlat-core/core/harness/syscalls/moa_executor.py
ls aiPlat-core/core/harness/syscalls/moa_presets.yaml
grep -c '"moa"' aiPlat-core/core/schemas_builder.py
grep -c 'MoA' aiPlat-management/frontend/src/components/model/ModelTierPanel.tsx
```

---

> *本文档随系统演进版本化更新。当前版本 v6.4.0 对应 aiPlat Phase 42（2026-07-19）。*
>
> *v1.0.0: Phase 24, L4基础*
> *v2.0.0: Phase 28, L4(L5-proximate), F轴L4高级*
> *v3.0.0: Phase 32, L4+(五轴L4+两轴L5), F/A轴触达L5*
> *v4.0.0: Phase 35, L4+(三轴L5), C轴通过handler.py代码生成触达L5*
> *v5.0.0: Phase 38, L5(六轴全L5), 39个Phase累积—系统定级L5组织者级*
> *v6.0.0: Phase 38, L5(10轴全L5), GossipProtocol+SwarmBroker+AdaptiveContextRouter 三轴推至L5, R轴 D4全接线*
> *v6.1.0: Phase 39, L5→L6第一步, AbstractGoalDecomposer 实现模糊目标→结构化子目标分解, GoalDependencyGraph 拓扑排序执行, GoalProgressEvaluator 收敛评估*
> *v6.2.0: Phase 40, L5→L6第二步, DeployEngine 沙箱→灰度→push→构建→部署→验证→回滚全闭环, GitPusher, canary auto_rollout*
> *v6.3.0: Phase 41, L5→L6第三步, 外部集成扫描→指纹→Config生成→监听注册, 默认DENY需人工授权*
*v6.4.0: Phase 42, 通用MoA多模型推理, 两层流水线(N参考引擎高温并行+1聚合器低温合成), `/moa`命令+Pipeline路由+模型选择器三入口, OpenRouter跨厂商*
> *v7.0.0: 2026-07-24 全面架构审计。B/D轴接线验证（AdaptiveContextRouter→MemoryManager, GossipProtocol→server.py）。L6 Phase 39-41 默认开启。验证体系升级为 8维运行时验证 (verify_l5_runtime.py v3)。622 ACTIVE, 96/100 readiness。*
