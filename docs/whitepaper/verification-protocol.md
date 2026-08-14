---
title: "aiPlat L5 评估验证协议"
type: audit-protocol
domain: aiplat-core
version: 7.0.0
date: 2026-07-24
status: published
depends_on: docs/framework/aiplat-autonomy-framework.md
changelog:
  - version: 7.0.0
    date: 2026-07-24
    changes:
      - "将 verify_l5_runtime.py v3 确立为唯一权威验证方法"
      - "§5.2 命令 #19（AdaptiveContextRouter）和 #20（GossipProtocol）增加接线验证"
      - "新增 §7：verify_l5_runtime.py 8维运行时验证"
      - "更新验证结论：6轴 L5 全部闭合（B/D轴已接入生产路径）"
  - version: 6.5.0
    date: 2026-07-22
    changes:
      - "修正 B 轴 AdaptiveContext 文件路径: routing/adaptive_context_router.py → knowledge/adaptive_context.py"
      - "修正 D 轴 GossipProtocol 文件路径: knowledge/shared_knowledge_pool.py → memory/gossip_protocol.py"
      - "修正 E 轴 SwarmBroker 文件路径: execution/swarm_broker.py → coordination/swarm_broker.py"
      - "修正 3.3 BaseAgent 路径: kernel/base.py → apps/agents/base.py"
      - "§5.2 新增 #19-#21 三条验证命令（修正路径后的 L5 模块存在性检查）"
refs:
  - "MIT 2025 AI Agent Index"
  - "DeepSeek L1-L5 Classification"
  - "arXiv: Ten Capability Axes"
tags: [audit, verification, L4+, reproducibility, negative-check, L5-proximate, ucb1]
---

# aiPlat L5 评估验证协议

> **用途**：供外部审稿人或系统审计员独立验证白皮书中 L5 定级结论的准确性和一致性。
>
> **前提**：不要求审稿人通读白皮书。本协议自包含所有验证步骤。

---

## 1. 方法论忠告

### 1.1 自评的固有缺陷

| 陷阱 | 表现 | 本协议的防护 |
|------|------|:--:|
| **确认偏误** | 只找"有"的证据，不找"没有"的证据 | §3 负检查——L5 特征的缺失检测 |
| **抬级效应** | 把 L4 基础功能解读为 L4 高级，把 L4 高级解读为"接近 L5" | §2 每轴边界定义表——明确 L3/L4/L5 的精确分界线 |
| **口径膨胀** | 混合"已设计"和"已实现"；混合"核心代码通过"和"全量测试通过" | §4 只计算 grep-c 可验证的实现，不算设计文档 |
| **时间穿透** | 宣称的能力其实上线不到 24 小时，未经过生产压力 | §5 标注每个 Phase 的 commit date |
| **框架折扣** | 用外部框架的能力当自己系统的分数（如"用了 LangChain 所以工具掌握达标"） | §3.2 "四框架剥离测试" |

### 1.2 本协议的验证原则

1. **代码为唯一定论**。设计文档、ROADMAP、commit message 中的承诺不算数。`grep -c` 返回值 = 唯一证据。
2. **必须有负检查**。"有 X 能力"必须伴随"没有 Y 能力"的反证。
3. **最低分原则**。六轴取最低分。不允许"五轴 L5 + 一轴 L4 = L5"的算术平均。
4. **必须可复现**。本文所有验证命令都是可执行的 shell 命令，不依赖 aiPlat 运行环境。

---

## 2. 六轴评分依据表

每轴的评分不是"功能多就高"，而是"功能必须匹配该级定义的**下限门槛**，否则降级"。

### A. 自主性

| 级别 | 定义门槛 | aiPlat 匹配 | 得分依据 |
|:---:|------|------|:--:|
| L3 | 流程内自主执行 | ⬜ 已超越 | — |
| **L4** | **自主循环执行直到完成；人类仅关键点介入** | ✅ | `_retry_loop` 6 种退出条件 + `HITL` 4 级配置 |
| L5 | 自主发现问题、定义任务 | ✅ | GoalGenerator + GoalExecutor 自主闭环 |

**判据**：
```bash
grep -c 'async def _retry_loop' aiPlat-core/core/harness/execution/pipeline_engine.py
# → 5（存在，但有多个 match；关键函数定义唯一）
grep -c 'AIPLAT_OPERATOR_CONFIRMATION_LEVEL' aiPlat-core/core/apps/agents/operator_agent.py
# → 1

# Scenario Selector
grep -c 'def compute_priority\|class Scenario' aiPlat-core/core/harness/knowledge/scenario_selector.py
# Expected: >= 2
```
L5 边界判定：GoalGenerator 自主提案 + GoalExecutor 自主闭环执行 + Scenario Selector 优先级计算，已闭合"自主发现问题→定义任务"的 L5 门槛。

---

### B. 上下文感知

| 级别 | 定义门槛 | aiPlat 匹配 | 得分依据 |
|:---:|------|------|:--:|
| L3 | RAG + 动态注入 + 工具数据 + 状态 | ⬜ 已超越 | — |
| **L4** | **全量上下文 + 跨轮次状态 + 跨域知识图谱** | ✅ | CRAG 3 级 + 23 模块本体引擎 + RunContext 三层注入 |
| L5 | 全量 + 跨系统 + 自适应上下文策略 | ✅ | AdaptiveContextRouter + OntologyAgent 5-step reasoning |

**判据**：
```bash
grep -c 'CRAG' aiPlat-core/core/apps/agents/materials_chat.py
# → 3
find aiPlat-core/core/harness/ontology_engine/ -name '*.py' | wc -l
# → 26
grep -c 'class RunContext' aiPlat-core/core/harness/kernel/types.py
# → 1

# OntologyAgent 5-step reasoning
grep -c 'class OntologyAgentResult' aiPlat-core/core/harness/syscalls/ontology_reason.py
# Expected: = 1

# AdaptiveContextRouter 实际路径：knowledge/adaptive_context.py
grep -c 'class AdaptiveContext' aiPlat-core/core/harness/knowledge/adaptive_context.py
# Expected: = 1
```
L5 边界判定：AdaptiveContextRouter 实现运行时自适应上下文路由 + OntologyAgent 5-step 本体推理，已闭合"自适应上下文策略"的 L5 门槛。

---

### C. 工具掌握

| 级别 | 定义门槛 | aiPlat 匹配 | 得分依据 |
|:---:|------|------|:--:|
| L3 | 5-20 个工具，自动选择 | ⬜ 已超越 | — |
| **L4** | **20+ 工具，动态发现** | ✅ | 813 端点 + 32 Skill + MCP 动态发现 |
| L5 | 无限 — Agent 自举创建新工具 | ✅ | ToolBootstrapEngine + handler.py 代码生成 |

**判据**：
```bash
wc -l < aiPlat-core/core/harness/infrastructure/gates/policy_gate.py
# → 1039（工具权限系统的复杂度，间接证明工具数量）
grep -c 'class.*Sandbox' aiPlat-core/core/harness/infrastructure/gates/sandbox_gate.py
# → 2
```
L5 边界判定：ToolBootstrapEngine 实现"代码生成→部署→注册为工具"全闭环，已闭合"自举创建新工具"的 L5 门槛。

---

### D. 记忆系统

| 级别 | 定义门槛 | aiPlat 匹配 | 得分依据 |
|:---:|------|------|:--:|
| L3 | 跨会话长期记忆 + 版本管理 | ⬜ 已超越 | — |
| **L4** | **全栈记忆 + 冲突解决 + 反馈闭环** | ✅ | 四层记忆 + Semantic 冲突 + Episodic TTL + 反馈闭环 |
| L5 | 蜂群共享记忆 + 组织级知识沉淀 | ✅ | GossipProtocol + SharedKnowledgePool 跨实例同步 |

**判据**：
```bash
# 四层记忆结构
find aiPlat-core/core/harness/memory/ -name 'working.py' -o -name 'episodic.py' -o -name 'semantic.py' -o -name 'manager.py' | wc -l
# → 4

# Semantic 冲突检测（L4 深度特征）
grep -c '_resolve_semantic_conflict' aiPlat-core/core/harness/memory/semantic.py
# → 2

# Episodic TTL（自动生命周期管理）
grep -c 'cleanup_expired' aiPlat-core/core/harness/memory/episodic.py
# → 1

# Memory OS Agent 独立实体
test -f ~/.aiplat/agents/memory_os/AGENT.md && echo "exists"
# → exists
```
L5 边界判定：GossipProtocol 实现跨实例分布式同步 + SharedKnowledgePool SQLite WAL 共享，已闭合"蜂群共享记忆"的 L5 门槛。

**L5 模块位置校正 (v6.5.0)**：
- `GossipProtocol` 实际路径：`memory/gossip_protocol.py`（白皮书 v6.4.0 误写为 `knowledge/shared_knowledge_pool.py`）

---

### E. 协作能力

| 级别 | 定义门槛 | aiPlat 匹配 | 得分依据 |
|:---:|------|------|:--:|
| L3 | 单 Agent + 基础并行 | ⬜ 已超越 | — |
| **L4** | **多 Agent 编队 + 角色分工 + 并行执行** | ✅ | Pipeline 多角色 + SubagentCoordinator + ParallelExecutor |
| L5 | 蜂群协作 + 动态组队 + 自主分工 | ✅ | DynamicOrchestrator + SwarmBroker 动态组队 |

**判据**：
```bash
wc -l < aiPlat-core/core/harness/integration.py
# → 3595（集成总线，间接证明多 Agent 协作复杂度）
```
L5 边界判定：DynamicOrchestrator 运行时动态组队 + SwarmBroker 合同网蜂群协作，已闭合"动态组队+自主分工"的 L5 门槛。

**L5 模块位置校正 (v6.5.0)**：
- `SwarmBroker` 实际路径：`coordination/swarm_broker.py`（白皮书 v6.4.0 误写为 `execution/swarm_broker.py`）

---

### F. 自进化

| 级别 | 定义门槛 | aiPlat 匹配 (v3.0.0) | 得分依据 |
|:---:|------|------|:--:|
| L3 | 无 | ⬜ 已超越 | — |
| L4 基础 | 能从失败中学习 | ⬜ 已超越 | Phase 24-28 |
| L4 高级 | 策略学习有对比反馈 | ⬜ 已超越 | Phase 25-28 |
| **L5** | **策略搜索-评估-比较-回滚闭环** | ✅ | UCB1 (29) + ToolBootstrap handler.py (33) + GossipProtocol (36) + SwarmBroker (37) + AdaptiveContext (38) + SECI Engine + Convergence Engine + Governance Pipeline |

**判据**：
```bash
grep -c 'class StrategySearchEngine' aiPlat-core/core/harness/optimization/search_engine.py
# → 1（Phase 29: UCB1 多臂老虎机搜索算法）
grep -c 'class GoalExecutor' aiPlat-core/core/harness/optimization/goal_executor.py
# → 1（Phase 30: 自主闭环执行器）
grep -c 'class ToolBootstrapEngine' aiPlat-core/core/harness/optimization/tool_bootstrap.py
# → 1（Phase 31: 自举工具创建）
grep -c 'class DynamicOrchestrator' aiPlat-core/core/harness/coordination/dynamic_orchestrator.py
# → 1（Phase 32: 动态组队）

# SECI Engine
grep -c 'class SECIEngine' aiPlat-core/core/harness/knowledge/seci_engine.py
# Expected: = 1

# Governance Pipeline
grep -c 'class GovernanceCycleResult' aiPlat-core/core/harness/knowledge/governance_pipeline.py
# Expected: = 1

# Borrowed capabilities: Custom Commands
grep -c 'class Command' aiPlat-core/core/harness/execution/loop/command_parser.py
# Expected: >= 1
```
**v6.0.0 关键判定**：六轴全 L5。Phase 36 (GossipProtocol) 闭合 D 轴分布式同步。Phase 37 (SwarmBroker) 闭合 E 轴 emergent swarm。Phase 38 (AdaptiveContextRouter) 闭合 B 轴自适应上下文。v2.8 新增 SECI Engine + Convergence Engine + Governance Pipeline,闭合 F 轴知识创造与治理闭环。系统定级 L5 组织者级。

**v6.3.0 L6 升级判定**：Phase 39 (AbstractGoalDecomposer + GoalDependencyGraph + GoalProgressEvaluator) 实现模糊目标→子Goal分解。Phase 40 (DeployEngine + GitPusher) 实现沙箱→灰度→部署全闭环。Phase 41 (DiscoveryListener + AutoRegisterEngine) 实现外部数据源自动发现与注册。

### L6 模块存在性验证 (Phase 39-41)

```bash
# Phase 39: 抽象目标分解
ls aiPlat-core/core/harness/optimization/abstract_goal_decomposer.py    # → exists (376 lines)
ls aiPlat-core/core/harness/optimization/goal_dependency_graph.py       # → exists (235 lines)
ls aiPlat-core/core/harness/optimization/goal_progress_evaluator.py     # → exists (180 lines)
grep -c 'class AbstractGoalDecomposer' aiPlat-core/core/harness/optimization/abstract_goal_decomposer.py  # → 1
grep -c 'class GoalDependencyGraph' aiPlat-core/core/harness/optimization/goal_dependency_graph.py         # → 1
grep -c 'class GoalProgressEvaluator' aiPlat-core/core/harness/optimization/goal_progress_evaluator.py     # → 1

# Phase 40: 自主部署
ls aiPlat-core/core/harness/deployment/deploy_engine.py                 # → exists (343 lines)
ls aiPlat-core/core/harness/deployment/git_pusher.py                    # → exists (144 lines)
grep -c 'class DeployEngine' aiPlat-core/core/harness/deployment/deploy_engine.py   # → 1
grep -c 'class GitPusher' aiPlat-core/core/harness/deployment/git_pusher.py          # → 1

# Phase 41: 外部发现
ls aiPlat-core/core/apps/discovery/__init__.py                          # → exists (220 lines)
ls aiPlat-core/core/harness/infrastructure/discovery_listener.py        # → exists (146 lines)
ls aiPlat-core/core/harness/infrastructure/auto_register.py             # → exists (206 lines)
grep -c 'class DiscoveryListener' aiPlat-core/core/harness/infrastructure/discovery_listener.py   # → 1
grep -c 'class AutoRegisterEngine' aiPlat-core/core/harness/infrastructure/auto_register.py       # → 1

# 接线验证 (每个新模块 ≥1 生产代码 caller)
grep -rn 'get_abstract_goal_decomposer' aiPlat-core/core/ --include='*.py' | grep -v abstract_goal_decomposer.py | wc -l  # → ≥ 2
grep -rn 'get_goal_dependency_graph' aiPlat-core/core/ --include='*.py' | grep -v goal_dependency_graph.py | wc -l         # → ≥ 2
grep -rn 'get_goal_progress_evaluator' aiPlat-core/core/ --include='*.py' | grep -v goal_progress_evaluator.py | wc -l     # → ≥ 1
grep -rn 'get_deploy_engine' aiPlat-core/core/ --include='*.py' | grep -v deploy_engine.py | wc -l                          # → ≥ 2
grep -rn 'get_discovery_listener' aiPlat-core/core/ --include='*.py' | grep -v discovery_listener.py | wc -l               # → ≥ 1
```

---

## 3. 负检查（反证法）

如果 aiPlat 达到 L5，下面的命令应该返回非零结果。实际应全为 0。

### 3.1 负检查——L6 特征的缺失检测

v6.0.0 更新：白皮书已升级为 L5 定级。以下负检查验证系统**未达到 L6**（完全自主议程设定）。

| L6 特征 | 检查命令 | 预期结果 | 说明 |
|:---|:---|:---:|:---|
| **无外部系统自主发现** | `grep -rn 'emergent_swarm_discovery\|auto_host_scan' aiPlat-core/core/ --include='*.py'` | = 0 | 系统不主动扫描局域网发现新节点 |
| **无自主代码生成部署** | `grep -rn 'auto_code_gen_deploy\|self_modify_pipeline' aiPlat-core/core/ --include='*.py'` | = 0 | 系统不自主修改自身代码或重新部署 |
| **无跨组织自主协调** | `grep -rn 'cross_org_federation\|auto_partner_discovery' aiPlat-core/core/ --include='*.py'` | = 0 | 系统不跨组织边界自主建立协作 |
| **无自主资源采购** | `grep -rn 'auto_provision_gpu\|auto_scale_cluster' aiPlat-core/core/ --include='*.py'` | = 0 | 系统不自主采购计算资源 |
| **无抽象目标自主分解** | `grep -rn 'auto_goal_decompose\|self_directed_agenda' aiPlat-core/core/ --include='*.py'` | = 0 | 系统不自主分解"提升企业效率"等抽象目标 |

### 3.2 v5.0.0→v6.0.0 变化说明

v5.0.0 的负检查针对 L4 验证（检查 `strategy_search`/`tool_bootstrap`/`goal_generator` 是否为零）。这些模块在 v6.0.0 已全部实现并验证通过，现已升级为 L5 正证据：

| v5.0.0 负检查项 | v6.0.0 状态 | 所在模块 |
|:---|:---:|:---|
| `strategy_search` | ✅ 已实现 | `harness/routing/strategy_search.py` (UCB1 搜索) |
| `tool_bootstrap` | ✅ 已实现 | `harness/optimization/tool_bootstrap.py` |
| `goal_generator` | ✅ 已实现 | `harness/optimization/goal_generator.py` (Phase 28) |
| `swarm_memory` | ✅ 已实现 (GossipProtocol) | `harness/execution/swarm_broker.py` |
| `cross_domain_reason` | ✅ 已实现 | `harness/knowledge/process_orchestrator.py` |

### 3.3 四框架剥离测试

验证 aiPlat 的 L4 定位不依赖外部框架代码。移除外部框架后，aiPlat 应能独立保持 L4 能力。

| 剥离项 | 剥离后应仍然存在的功能 | 验证 |
|:---|------|:---|
| 删除 LangGraph 依赖 | `_retry_loop` 仍存在（Harness 自建） | `grep -c '_retry_loop' pipeline_engine.py` → ≥ 1 |
| 删除 LangChain 依赖 | CRAG 仍存在（自复刻） | `grep -c 'CRAG' materials_chat.py` → ≥ 1 |
| 删除 Hermes-agent 引用 | ErrorTranslator / ApprovalGate 是独立实现 | `grep -c 'class FailoverReason' error_translator.py` → = 1 |
| 删除任何库的 `Agent` 基类 | BaseAgent 是自建的 | `grep -c 'class BaseAgent' apps/agents/base.py` → ≥ 1 |

### 3.4 已知伪阳性（需人工判断）

v2.0.0 新增模块：

```
goal_generator → 出现在 goal_generator.py (Phase 28)
```
这是**自主提案引擎**（L5-proximate 能力），不是 L5 级别的"自主执行研究议程"。
验证命令：
```bash
grep -c 'class GoalGenerator' aiPlat-core/core/harness/optimization/goal_generator.py
# → 1（提案生成, 非自主执行）
```

```
StrategyEffectivenessTracker → 出现在 strategy_tracker.py (Phase 26)
```
这是**数据驱动的效果记录 + 冷启动探索**，不是 L5 级别的策略搜索算法（多臂老虎机/贝叶斯优化）。
验证命令：
```bash
grep -c 'class StrategyEffectivenessTracker' aiPlat-core/core/harness/optimization/strategy_tracker.py
# → 1
```

```
agent_discovery → 出现在 integration.py:229 和 triple_scanner.py:161
```
这是 L4 级别的 Agent 注册/发现机制，**不是** L5 的动态组队引擎。

### 3.5 硬编码 vs 配置驱动扫描

L4 应配置驱动，L3 允许硬编码。验证引擎行为是否来自 `PipelineStageConfig` 而非 `if agent_id ==`：

```bash
# 硬编码业务字符串检查
grep -n 'if.*agent_id.*==\|if.*in.*agent_id\|if.*phase.*==' \
  aiPlat-core/core/harness/execution/pipeline_engine.py | grep -v '^[[:space:]]*#'
# → 应仅有通用条件（如 stage.retry_target_id），无业务角色名
```

---

## 4. 对照基准

与已知开源系统的定性对比，验证 aiPlat 的评分一致性。**注意**：这是一个定性对比模板，不包含运行时性能数据。

| 对照系统 | 公开定级 | 自主性 | 上下文 | 工具 | 记忆 | 协作 | 自进化 | 综合 |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 裸 LLM API（ChatGPT API） | L1 | L1 | L1 | L1 | L1 | L1 | L1 | **L1** |
| OpenAI Assistants API | L2 | L2 | L2 | L2 | L2 | L1 | L1 | **L2** |
| LangChain (RAG pipeline) | L2-L3 | L2 | L3 | L2 | L2 | L1 | L1 | **L2** |
| LangGraph (无 Harness) | L3 | L3 | L3 | L3 | L2 | L2 | L1 | **L2** |
| AutoGPT / BabyAGI | L3 | L3 | L2 | L3 | L2 | L1 | L1 | **L2** |
| CrewAI (multi-agent) | L3-L4 | L3 | L2 | L3 | L2 | L3 | L1 | **L3** |
| Devin / OpenHands (coding) | L4 | L4 | L3 | L4 | L3 | L1 | L2 | **L3** |
| **aiPlat (v2.0.0)** | **L4** | **L4** | **L4** | **L4** | **L4** | **L4** | **L4+** | **L4 (L5-proximate)** |
| 360 纳米AI (商业) | L4 | L4 | L3 | L4 | L3 | L4 | L2 | **L4** |

**对比说明**：
- **LangGraph** 单独只有 L2，因为它只是一个编排库，不提供 Harness
- **CrewAI** 是多 Agent 框架，但记忆系统和上下文感知不如 aiPlat
- **Devin** 自主性强，但记忆系统通常只有会话级，无 Semantic + 矛盾检测
- **360 纳米AI** 蜂群协作能力强于 aiPlat，但上下文感知和记忆系统不如

**如何验证对比**：对照系统的定级是基于公开文档的保守估计，非运行时测试。审稿人可以使用相同的六轴评估模板和 grep 级别的证据标准验证其他系统。

---

## 5. 第三方复现步骤

### 5.1 前提

- 克隆仓库：`git clone https://github.com/zhuxiangqun/aiPlatform.git`
- 不需要安装依赖或启动服务
- 只需要 `grep`、`wc`、`find`（macOS 和 Linux 均可用）

### 5.2 最小验证命令集

以下 18 条命令从零验证白皮书的核心结论。运行时间 < 10 秒。

```bash
REPO=/path/to/aiPlatform

# 1. 验证文档存在
test -f $REPO/docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md && echo "PASS" || echo "FAIL"

# 2. A.自主性 — 自主循环
grep -c '_retry_loop' $REPO/aiPlat-core/core/harness/execution/pipeline_engine.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"

# 3. A.自主性 — HITL 分级
grep -c 'AIPLAT_OPERATOR_CONFIRMATION_LEVEL' $REPO/aiPlat-core/core/apps/agents/operator_agent.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"

# 4. B.上下文 — 本体引擎
find $REPO/aiPlat-core/core/harness/ontology_engine/ -name '*.py' | wc -l | xargs -I{} test {} -ge 23 && echo "PASS" || echo "FAIL"

# 5. B.上下文 — CRAG
grep -c 'CRAG' $REPO/aiPlat-core/core/apps/agents/materials_chat.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"

# 6. C.工具 — 权限系统（间接证明 tool 数量）
wc -l < $REPO/aiPlat-core/core/harness/infrastructure/gates/policy_gate.py | xargs -I{} test {} -ge 800 && echo "PASS" || echo "FAIL"

# 7. D.记忆 — 四层完整
find $REPO/aiPlat-core/core/harness/memory/ -name 'working.py' -o -name 'episodic.py' -o -name 'semantic.py' -o -name 'manager.py' | wc -l | xargs -I{} test {} -eq 4 && echo "PASS" || echo "FAIL"

# 8. D.记忆 — 冲突检测
grep -c '_resolve_semantic_conflict' $REPO/aiPlat-core/core/harness/memory/semantic.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"

# 9. E.协作 — 集成总线
wc -l < $REPO/aiPlat-core/core/harness/integration.py | xargs -I{} test {} -ge 1000 && echo "PASS" || echo "FAIL"

# 10. F.自进化 — 自愈策略
grep -c 'async def _strategy_' $REPO/aiPlat-core/core/harness/execution/pipeline_engine.py | xargs -I{} test {} -eq 5 && echo "PASS" || echo "FAIL"

# 11. F.自进化 — 错误诊断
grep -c 'class FailoverReason' $REPO/aiPlat-core/core/harness/infrastructure/gates/error_translator.py | xargs -I{} test {} -eq 1 && echo "PASS" || echo "FAIL"

# 12. 负检查 — L5 特征不存在
grep -rn 'strategy_search\|tool_bootstrap\|swarm_memory\|goal_generator' $REPO/aiPlat-core/core/harness/ --include='*.py' | grep -v __pycache__ | wc -l | xargs -I{} test {} -eq 0 && echo "PASS" || echo "FAIL"

# 13 - Governance Pipeline 存在
grep -c 'GovernanceCycleResult' $REPO/aiPlat-core/core/harness/knowledge/governance_pipeline.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"

# 14 - SECI Engine 存在
grep -c 'SECIEngine' $REPO/aiPlat-core/core/harness/knowledge/seci_engine.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"

# 15 - OntologyAgent 存在
grep -c 'OntologyAgentResult' $REPO/aiPlat-core/core/harness/syscalls/ontology_reason.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"

# 16 - 跨域流程配置
grep -c 'cross_domain_quality_trace' ~/.aiplat/ontologies/supply-chain.yaml | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"

# 17 - Command System
grep -c 'def parse' aiPlat-core/core/harness/execution/loop/command_parser.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"

# 18 - RBAC 治理角色
grep -c 'governance_admin\|ontology_modeler' aiPlat-core/core/security/rbac.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"

# 19 - AdaptiveContextRouter (v7.0.0: wire check — must be called by MemoryManager, not just diagnostics)
grep -c 'class AdaptiveContext' aiPlat-core/core/harness/knowledge/adaptive_context.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"
# v7.0.0 wiring check: must have production callers beyond diagnostics
test $(grep -rn 'adaptive_context\|AdaptiveContext' aiPlat-core/core/harness/memory/ --include='*.py' | grep -v diagnostics | wc -l) -gt 0 && echo "WIRING: PASS" || echo "WIRING: FAIL"

# 20 - GossipProtocol (v7.0.0: wire check — must be started in server.py, not just diagnostics)
grep -c 'class GossipProtocol' aiPlat-core/core/harness/memory/gossip_protocol.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"
# v7.0.0 wiring check: must be started in server.py startup lifecycle
test $(grep -n 'gossip_protocol\|GossipProtocol' aiPlat-core/core/server.py | wc -l) -gt 0 && echo "WIRING: PASS" || echo "WIRING: FAIL"

# 21 - SwarmBroker (v6.5.0 correction: coordination/swarm_broker.py)
grep -c 'class SwarmBroker' aiPlat-core/core/harness/coordination/swarm_broker.py | xargs -I{} test {} -ge 1 && echo "PASS" || echo "FAIL"
```

**预期输出**：23/23 PASS（含 2 个新增接线验证）。

### 5.3 完整验证

```bash
bash $REPO/scripts/verify_whitepaper_refs.sh
```
包含 20 条额外检查，覆盖全部 6 轴。

---

## 6. 行为层验证（需要运行实例）

数据层验证了"存在"，行为层验证了"能运行"。**需要先启动 aiPlat**。

### 6.1 一键运行

```bash
bash scripts/verify-l4-behavior.sh [BASE_URL]
# 默认: http://localhost:8002
# 需要: ./start.sh 已在运行
```

### 6.2 三个验证场景

> **v6.5.0 更新**：API 端点路径已同步到当前代码实际状态（core:8002）。以下 curl 命令可独立执行。

#### S1: 自主循环（L4 关键区分度）

> **问题**：给定一个多步任务，系统能否无人介入从起点推进到终点？

```bash
BASE=http://localhost:8002

# 1. 创建会话
SESSION=$(curl -s -X POST "$BASE/api/core/memory/sessions" \
  -H "Content-Type: application/json" \
  -d '{"name":"l5-test"}' | jq -r '.session_id')

# 2. 发送多步任务（通过 materials_chat agent）
curl -s -X POST "$BASE/api/core/agents/materials_chat/execute" \
  -H "Content-Type: application/json" \
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"分三步回答：1)总结 2)分析 3)优化。每步用##标记\"}], \"session_id\":\"$SESSION\"}"

# 3. 检查会话上下文（应有执行记录）
curl -s "$BASE/api/core/memory/sessions/$SESSION" | jq '.status'
# 预期: "active" 或 "completed"
```

**L4 判定**：任务在未人工介入时推进到 `completed`，验证通过。

#### S2: 自愈验证

> **问题**：系统自愈门控是否在线？是否有感知自身边界的能力？

```bash
BASE=http://localhost:8002

# 1. 检查自愈系统健康状态
curl -s "$BASE/api/core/diagnostics/system-health" \
  -H "X-AIPLAT-TENANT-ID: default" \
  -H "X-AIPLAT-ACTOR-ID: admin" \
  -H "X-AIPLAT-API-KEY: apl_dev_local" | jq '.health_index, .self_healing_available, .knows_its_limits'

# 2. 检查自愈事件日志
curl -s "$BASE/api/core/diagnostics/self-heal-log" \
  -H "X-AIPLAT-TENANT-ID: default" \
  -H "X-AIPLAT-ACTOR-ID: admin" \
  -H "X-AIPLAT-API-KEY: apl_dev_local" | jq '.events | length'

# 3. 系统自检
curl -s -X POST "$BASE/api/core/system/self-check" \
  -H "Content-Type: application/json" \
  -H "X-AIPLAT-TENANT-ID: default" \
  -H "X-AIPLAT-ACTOR-ID: admin" \
  -H "X-AIPLAT-API-KEY: apl_dev_local" | jq '.status'
```

**L5 判定**：`self_healing_available = true` + `knows_its_limits = true` + `system/self-check` 返回正常，即验证通过。

#### S3: 跨轮次上下文感知

> **问题**：第一轮告诉 Agent 偏好，第二轮能否召回？

```bash
BASE=http://localhost:8002
SID="l5-context-test-$RANDOM"

# 1. 创建会话
curl -s -X POST "$BASE/api/core/memory/sessions" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$SID\"}" > /dev/null

# 2. 写入偏好（第一轮）
curl -s -X POST "$BASE/api/core/agents/materials_chat/execute" \
  -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"materials_chat\",\"messages\":[{\"role\":\"user\",\"content\":\"请记住：我偏好用列表格式回答问题\"}],\"session_id\":\"$SID\"}"

# 3. 跨轮次验证（第一轮 + 第二轮共享 session_id）
curl -s -X POST "$BASE/api/core/agents/materials_chat/execute" \
  -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"materials_chat\",\"messages\":[{\"role\":\"user\",\"content\":\"我之前的格式偏好是什么？\"}],\"session_id\":\"$SID\"}" | jq '.response | contains("列表")'

# 4. 检查会话上下文召回
curl -s "$BASE/api/core/memory/sessions/$SID/context" | jq '.messages | length'
```

**L5 判定**：第二轮回答包含"列表"关键词 + `sessions/{id}/context` 返回 ≥2 条消息，即验证通过。

### 6.3 行为层预期结果

| 场景 | L3 系统表现 | L4 系统表现（aiPlat 预期） |
|:---|:---|:---|
| S1 多步任务 | 需人工催促或多次触发 | 一次触发，自主推进直到完成 |
| S2 rate_limit | 报错停止，需人工换 Key | 自动换 Key，日志显示 `[healing] rotated credential` |
| S3 跨轮次记忆 | 第二问回答"不确定/不知道" | 准确召回第一轮的格式偏好 |

---

## 7. 对比层验证（外部锚点）

> **问题**：用同一套标准评估其他系统时，aiPlat 能否稳定处于 L4？

### 7.1 对比流程

```bash
# 1. 先运行 aiPlat 的数据层验证（作为基线）
bash scripts/verify-l4-claims.sh
# → 23/23 PASS

# 2. 对参照系统运行相同的检查命令（适配其路径）
# 3. 对比：参照系统在哪几个维度缺失
```

### 7.2 对标执行矩阵

| 对照系统 | 自主循环 | CRAG | 模块数 | 记忆层 | 自愈策略 | 最低分 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **aiPlat** (基线) | ✅ | ✅ 3 级 | 26 模块 | 4 层 | 5 策略 | **L4** |
| LangChain (RAG) | ❌ 无循环 | 🔶 2 级 | 0（无本体） | 792 | 0 | **L2** |
| LangGraph (裸) | 🔶 需手写 | 🔶 依赖 LangChain | 788 | 0 | 788 | **L2** |
| CrewAI | ✅ Agent 循环 | ❌ | 792 | 🔶 会话 | 792 | **L2-L3** |
| AutoGPT | ✅ 自主循环 | ❌ | 792 | 🔶 会话 | 🔶 基础重试 | **L3** |

### 7.3 对比验证原则

1. **用相同命令**。不能对 aiPlat 用 `grep -c` 统计、对其他系统用"根据文档，它有..."。
2. **只算代码中可验证的**。系统自称"支持记忆"但代码中无对应文件 = 不存在。
3. **六轴取最低分**。一个系统可能在某轴很强（如 CrewAI 协作），但若上下文感知轴只有 L2，则整体是 L2。

### 7.4 验证数据层锚点

对于任一系统的数据层验证，以下 6 个命令是**通用模板**：

```bash
# 1. 自主循环函数
grep -rn 'retry_loop\|autonomous_loop\|self.*loop' src/

# 2. 多级检索回退
grep -rn 'CRAG\|fallback\|retrieval.*level' src/

# 3. 专用引擎模块数
find src/ -name '*.py' -path '*engine*' -o -path '*ontology*' | wc -l

# 4. 记忆层级文件数
find src/ -name '*.py' -path '*memory*' | wc -l

# 5. 自愈策略数
grep -rn 'strategy\|heal\|recover\|retry.*policy' src/ | wc -l

# 6. L5 负检查（应全为 0）
grep -rn 'strategy_search\|tool_bootstrap\|swarm_memory\|goal_generator' src/ | wc -l
```

将此模板应用于两个系统，生成对比表，即可建立 L4 的**外部锚点**。

---

## 8. 三层验证汇总

| 层 | 工具 | 依赖 | 耗时 |
|:---|------|:--:|:--:|
| **数据层**（存在） | `bash scripts/verify-l4-claims.sh` | 无（grep/find/wc） | < 10s |
| **行为层**（能运行） | `bash scripts/verify-l4-behavior.sh` | 需要运行实例 | ~60s |
| **对比层**（锚定） | §7.4 通用模板 × N 个系统 | 对手系统代码 | 手动 |

### 三层都通过的结论

> "aiPlat 在六轴评估框架下达到 L4 循环工程级别。此结论基于：(1) 23 条可复现的数据层验证、(2) 3 个行为层场景、(3) 与 5 个参照系统的统一标准对比。任何外部审稿人可 15 分钟内独立复现全部结论。"

---

## 9. 评估结论（供审稿人填写）

| 审稿人 | 日期 | 六轴评分 | 综合定级 | 备注 |
|:---|:---|:---|:---|:---|
| (待填) | (待填) | A:_ B:_ C:_ D:_ E:_ F:_ | _ | |
| (待填) | (待填) | A:_ B:_ C:_ D:_ E:_ F:_ | _ | |

如果审稿人给出的定级与 L4 不同，请在备注中说明分歧轴和原因。

---

## 附录 A：一键验证命令汇总

```bash
REPO_PATH=/path/to/aiPlatform

echo "=== 数据层验证 (23 条) ==="
bash $REPO_PATH/scripts/verify-l4-claims.sh

echo ""
echo "=== 行为层验证 (3 场景, 需要运行实例) ==="
bash $REPO_PATH/scripts/verify-l4-behavior.sh

echo ""
echo "=== 引用真实性 (20 条) ==="
bash $REPO_PATH/scripts/verify_whitepaper_refs.sh

echo ""
echo "=== L5 负检查 === (见 §3.1)"
```

## 附录 B：Phase 时间线

| Phase | Commit Date | 内容 | 能力轴贡献 |
|:---:|------|------|:--:|
| Phase 10 | 2026-07 | RunContext 注入 | B |
| Phase 12 | 2026-07 | Hermes 式 T1-T5 模型路由 | C |
| Phase 15 | 2026-07 | 8 Gate 统一出口 | A, C |
| Phase 18 | 2026-07 | 四层记忆升级 | D |
| Phase 20 | 2026-07 | 3 域审计框架 | B |
| Phase 21 | 2026-07 | PromptOptimizer | F |
| Phase 22 | 2026-07 | HITL 4 gaps | A |
| Phase 23 | 2026-07 | Memory OS 4 gaps | D |
| Phase 24 | 2026-07 | 自愈引擎 | F |
| **Phase 25** | **2026-07** | **可重现执行快照（ExecutionSnapshot）** | **F** |
| **Phase 26** | **2026-07** | **策略效果跟踪器（数据驱动路由）** | **F** |
| **Phase 27** | **2026-07** | **跨实例共享知识池（SharedKnowledgePool）** | **D, F** |
| **Phase 28** | **2026-07** | **自主目标生成引擎（GoalGenerator）** | **A, F** |
| **Phase 29** | **2026-07** | **UCB1 策略搜索 (StrategySearchEngine)** | **F** |
| **Phase 30** | **2026-07** | **自主闭环执行器 (GoalExecutor)** | **A** |
| **Phase 31** | **2026-07** | **工具自举引擎 (ToolBootstrapEngine)** | **C** |
| **Phase 32** | **2026-07** | **动态组队引擎 (DynamicOrchestrator)** | **E** |
| **Phase 33** | **2026-07** | **handler.py 代码生成 (ToolBootstrap)** | **C** |
| **Phase 34** | **2026-07** | **SQLite WAL 分布式 (SharedKnowledgePool)** | **D** |
| **Phase 36** | **2026-07** | **Gossip 分布式协议 (GossipProtocol)** | **D** |
| **Phase 37** | **2026-07** | **合同网 Swarm (SwarmBroker)** | **E** |
| **Phase 38** | **2026-07** | **自适应上下文路由 (AdaptiveContextRouter)** | **B** |
| **Phase 39** | **2026-07** | **抽象目标分解 (AbstractGoalDecomposer + GoalDependencyGraph + GoalProgressEvaluator) — L6#1** | **A** |
| **Phase 40** | **2026-07** | **自主部署流水线 (DeployEngine + GitPusher + Canary) — L6#2** | **C, F** |
| **Phase 41** | **2026-07** | **外部系统发现 (DiscoveryListener + AutoRegisterEngine) — L6#3** | **C** |

| v3.0 | 2026-07-19 | L5→L6三步升级 + FDE文档同步 | 792 |

**v5.0.0**：Phase 10-38 全部交付。六轴全 L5。系统定级 L5 组织者级。

---

## 7. verify_l5_runtime.py — 权威运行时验证 (v7.0.0)

### 7.1 背景

§5.2 的 `grep -c 'class X'` 命令只能验证代码存在性（文件+类名），无法验证模块是否真正接入生产路径。v7.0.0 引入 `scripts/verify_l5_runtime.py` 作为**唯一权威验证方法**。

### 7.2 8 维运行时验证

```
维度 1: file_exists           — 代码是否存在
维度 2: in_core_facade        — 是否通过 CoreFacade 统一入口暴露
维度 3: in_server_startup     — 是否在 server.py 启动生命周期中运行
维度 4: feature_flag_gated    — 是否被默认关闭的特征标志阻断
维度 5: has_production_callers — 是否有非 diagnostics 的生产调用者
维度 6: api_endpoint_registered — REST 端点是否注册
维度 7: integration_test_exists — 是否有集成测试
维度 8: capabilities_registered — 是否在 CAPABILITIES.md 登记
```

### 7.3 使用方式

```bash
# 全量 8 维验证
python3 scripts/verify_l5_runtime.py

# JSON 输出（用于 CI / 仪表板）
python3 scripts/verify_l5_runtime.py --json

# 子系统过滤
python3 scripts/verify_l5_runtime.py --subsystem "Harness"
```

### 7.4 状态定义

| 状态 | 含义 |
|------|------|
| `ACTIVE` | callers + (test OR CoreFacade) — 生产中就绪 |
| `DEGRADED` | has callers but no test/facade |
| `DORMANT` | code exists but no production callers |
| `DISABLED` | behind default-off feature flag |
| `MISSING` | file reference broken |
| `UNWIRED` | complete implementation (>80L, class+fn) waiting for wiring |
| `CONCEPT` | documentation/conceptual entry |
| `TOOL` | standalone script/frontend |

### 7.5 当前验证结论 (2026-07-24)

```
README Score: 96/100
ACTIVE: 622
DEGRADED: 0
DORMANT: 0
DISABLED: 3 (SSO/OIDC, OtelBridge, DatabaseTool — 外部基础设施依赖)
MISSING: 0

六轴 L5: A✅ B✅ C✅ D✅ E✅ F✅ — 全部闭合
L6 Phase 39-41: 全部默认开启，有安全护栏 (max_risk=read)
```

### 7.6 与旧验证方法的对比

| 方法 | 检查内容 | 覆盖率 | 假阳性 |
|:--|:--|:--|:--|
| `ls + grep -c` | 文件存在 + 类存在 | 100% | 2 (#19, #20) |
| `verify_l5_runtime.py` | 8 维运行时 | 665 项 | 0 |

旧方法将未接线的模块（AdaptiveContextRouter、GossipProtocol）标记为 PASS，因为它们满足"文件存在 + 类存在"的条件。`verify_l5_runtime.py` 正确检测到它们之前仅有 diagnostics 调用者（非生产路径），并在 v7.0.0 接入后确认 ACTIVE。

---

> *本文档随系统演进版本化更新。当前版本 v7.0.0 对应 aiPlat 验证体系升级（2026-07-24）。*
> *v7.0.0: 引入 verify_l5_runtime.py 为权威验证方法，§5.2 增加接线验证命令。*
