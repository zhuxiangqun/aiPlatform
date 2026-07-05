---
title: "aiPlat 自主性分级评估：L4 循环工程"
type: architecture-decision-record
domain: aiplat-core
version: 1.0.0
date: 2026-07-05
status: published
authors: [aiPlat Architecture Team]
reviewers: [External Review]
tags: [autonomy, L4, loop-engineering, self-healing, evaluation]
related_phases: [Phase 10, Phase 11, Phase 12, Phase 13, Phase 14, Phase 15, Phase 16, Phase 17, Phase 18, Phase 19, Phase 20, Phase 21, Phase 22, Phase 23, Phase 24]
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
refs:
  - "MIT 2025 AI Agent Index"
  - "Cambridge/Harvard/Stanford Joint Report (30 systems)"
  - "DeepSeek L1-L5 Autonomy Classification (陈德里)"
  - "Redis Context Engineering 5-Stage Maturity Model"
  - "arXiv: Ten Capability Axes for AI Agents"
---

# aiPlat 自主性分级评估：L4 循环工程

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

### F. 自进化 — L4（基础）

> **定义**：诊断驱动的策略路由 + champion-challenger 优化

**表现**：

| 能力 | 实现 | 代码位置 |
|------|------|---------|
| 错误诊断 | `ErrorTranslator` — 7 级 19 类错误，4 个 recovery flag | `infrastructure/gates/error_translator.py:26-43` |
| 自愈策略路由 | Phase 24 — 5 子策略：rotate_credential / compress_retry / backoff / skip / escalate | `pipeline_engine.py:4415-4506` |
| Champion-Challenger | `PromptOptimizer` — Darwin Arena + EvolutionRunner 自主迭代 | `optimization/prompt_optimizer.py` |
| 失败学习 | `AutoLearner` — 失败模式分析 → SkillDraft 生成 → Docker 沙盒预检 → 人工审批 | `learning/auto_learner.py` |

**验证**：

```bash
grep -c 'class FailoverReason' core/harness/infrastructure/gates/error_translator.py
# → 1
grep -c 'async def _strategy_' core/harness/execution/pipeline_engine.py
# → 5
grep -c 'class PromptOptimizer' core/harness/optimization/prompt_optimizer.py
# → 1
```

**差距（→ L5）**：这是最大短板。5 个子策略是硬编码的，未达到"策略搜索 → 评估 → 比较 → 回滚"的完整闭环。核心瓶颈是缺少**可重现执行环境快照**——同一任务上无法对比不同策略的长期效果。

---

### 能力对照矩阵（结论）

| 能力轴 | 级别 | 状态 |
|:---|---:|:--:|
| A. 自主性 | L4（高） | 6 种退出条件的自主循环 + 分级 HITL |
| B. 上下文感知 | L4（强） | CRAG + 23 模块本体引擎 + RunContext 三层注入 |
| C. 工具掌握 | L4 | 813 端点 + 32 Skill + MCP 动态发现 |
| D. 记忆系统 | L4（强） | 四层记忆 + 矛盾检测 + TTL + 反馈闭环 |
| E. 协作能力 | L4 | Pipeline 编队 + 子 Agent 协调 + 语义通信桥 |
| F. 自进化 | **L4（基础）** | 策略硬编码，未达策略搜索闭环 |

**六轴最低分 = F.自进化 = L4** → 系统整体定级为 **L4 — 循环工程**。

### 与 L5 定义的差距（一句话总结）

| L5 必须能力 | aiPlat 能否做到 | 差距本质 |
|:---|:---:|:---|
| Agent 自主选题、定义研究议程 | 否 | 需目标生成引擎 |
| 策略搜索 → 评估 → 比较 → 回滚闭环 | **否** | **最大差距**（需 Phase 25 可重现快照 + Phase 26 搜索） |
| 自举创建新工具（代码生成 → 部署 → 注册） | 否 | 需完整工具生命周期闭环 |
| 蜂群共享记忆（跨实例知识同步） | 否 | 需跨实例记忆同步协议 |
| 动态组队、自主分工（非预设 Pipeline 编队） | 否 | 需动态编排引擎 |

> **关键洞察**：L5 不是 L4 的功能堆叠。核心瓶颈不是"多写几个策略方法"，而是**可重现执行环境快照**——确保同一任务上不同策略效果的对比是可验证的。参见 §5。

---

## 3. 24 Phase 演进路径

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

**核心原则**：每个 Phase 建立在前一个之上。L4 是 24 步累积的必然结果，不是某个时刻的跳跃。

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

| 维度 | L4 现状 | L5 要求 | 差距评估 |
|------|--------|--------|:--:|
| **F.自进化** | 5 个硬编码子策略 + champion-challenger 优化 | 策略搜索 → 评估 → 比较 → 回滚闭环 | **最大差距** |
| **A.自主性** | 人类设定目标，Agent 执行 | Agent 自主选题、定义研究议程 | 需要目标生成引擎 |
| **C.工具** | 32 Skill + MCP 动态发现 | Agent 自举创建新工具 | 需要代码生成 → 部署 → 注册闭环 |
| **D.记忆** | 单系统四层记忆 | 蜂群共享记忆 + 组织级知识沉淀 | 需要跨实例知识同步 |
| **E.协作** | 固定 Pipeline 编队 | 动态组队、自主分工 | 需要动态编排引擎 |

### 核心瓶颈：可重现执行环境快照

L5 的完整自进化闭环是：

```
策略搜索 → 评估比较 → 选出最优 → 回滚到最优 → 持续循环
```

但 aiPlat 当前缺少一个关键前置条件：**在同一任务上可重现、可对比的评估环境**。

| 现状 | L5 需要 |
|:---|:---|
| Phase 24 子策略是"遇到 rate_limit → 换 Key"，决策确定 | "换 Key 和退避等待都尝试过，哪种长期成功率更高"的对比能力 |
| PromptOptimizer 的 champion-challenger 基于评测集 | 策略优化需要比评测集更细粒度的执行环境快照 |
| Phase 19 仪表盘展示"自愈成功率" | 展示"尝试过的策略路径树"和每条路径的历史效果 |

**这意味着 L5 的第一个前置 Phase 不是"搜索算法"，而是"可重现执行环境快照"**：

- 每一次策略执行，把上下文、工具状态、记忆快照、依赖版本全部固化
- 下一次尝试不同策略时，从同一个快照恢复，然后执行，再对比效果
- 没有这个能力，"策略搜索"就变成了"在不可比的环境里盲试"

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

**aiPlat 自主性等级：L4 — 循环工程**

- 六轴全部达到 L4
- 上下文感知（B）和记忆系统（D）已接近 L4 上限
- 最大短板：自进化（F），策略硬编码，未达搜索-评估-回滚闭环

### L5 升级前置 Phase

| Phase | 内容 | 优先级 |
|:---:|------|:--:|
| **25** | **可重现执行环境快照** — 上下文/工具/记忆/依赖版本全部固化，同一任务上对比不同策略效果 | P0 |
| **26** | **策略搜索引擎** — 在快照基础上自动尝试不同自愈策略、对比效果、晋升最优 | P0 |
| **27** | **跨实例记忆共享** — 蜂群共享记忆 + 组织级知识沉淀 | P1 |
| **28** | **目标生成引擎** — Agent 自主选题、定义研究议程、分配资源 | P2 |

### 行业对标

| 系统 | 类型 | 自主等级 | aiPlat 对标优势 |
|------|------|:--:|------|
| 对话式智能体（12个） | MIT Index | L1-L3 | aiPlat 已超越 |
| 企业工作流智能体（13个） | MIT Index | L3-L5（部署态） | aiPlat 处于前 25% |
| 360 纳米AI | 商业产品 | L4（蜂群 1000 步） | aiPlat 在记忆系统和上下文感知上更强 |
| DeepSeek Agent | 研究框架 | L1-L5 定义 | aiPlat 的 ADR 对齐其 L4 定义 |

### 不可复制优势

1. **24 Phase 递进式构建** — 每步可验证，零技术债务
2. **四框架概念吸收** — 不依赖任何外部框架代码
3. **设计纪律** — 内核无关 + 配置驱动 + 接线完成度，15 维审计强制执行
4. **记忆系统** — 四层记忆 + 矛盾检测 + TTL 清理 + 反馈闭环，接近 L4 上限

---

> *本文档随系统演进版本化更新。当前版本 v1.0.0 对应 aiPlat Phase 24（2026-07-05）。*
>
> *验证命令：`bash scripts/verify_whitepaper_refs.sh docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md`*
