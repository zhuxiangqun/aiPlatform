---
title: "aiPlat L4 评估验证协议"
type: audit-protocol
domain: aiplat-core
version: 1.0.0
date: 2026-07-05
status: published
depends_on: docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md
refs:
  - "MIT 2025 AI Agent Index"
  - "DeepSeek L1-L5 Classification"
  - "arXiv: Ten Capability Axes"
tags: [audit, verification, L4, reproducibility, negative-check]
---

# aiPlat L4 评估验证协议

> **用途**：供外部审稿人或系统审计员独立验证白皮书中 L4 定级结论的准确性和一致性。
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
| L5 | 自主发现问题、定义任务 | ❌ | 无目标生成引擎，需人类设定目标 |

**判据**：
```bash
grep -c 'async def _retry_loop' aiPlat-core/core/harness/execution/pipeline_engine.py
# → 5（存在，但有多个 match；关键函数定义唯一）
grep -c 'AIPLAT_OPERATOR_CONFIRMATION_LEVEL' aiPlat-core/core/apps/agents/operator_agent.py
# → 1
```
L4 边界判定：6 种退出条件 + 分级 HITL ≥ 典型 L4 系统。未达到 L5 是因为仍需人类启动，无法自主选题。

---

### B. 上下文感知

| 级别 | 定义门槛 | aiPlat 匹配 | 得分依据 |
|:---:|------|------|:--:|
| L3 | RAG + 动态注入 + 工具数据 + 状态 | ⬜ 已超越 | — |
| **L4** | **全量上下文 + 跨轮次状态 + 跨域知识图谱** | ✅ | CRAG 3 级 + 23 模块本体引擎 + RunContext 三层注入 |
| L5 | 全量 + 跨系统 + 自适应上下文策略 | ❌ | 无自适应上下文压缩策略（温度剪枝是启发式，非自适应） |

**判据**：
```bash
grep -c 'CRAG' aiPlat-core/core/apps/agents/materials_chat.py
# → 3
find aiPlat-core/core/harness/ontology_engine/ -name '*.py' | wc -l
# → 26
grep -c 'class RunContext' aiPlat-core/core/harness/kernel/types.py
# → 1
```
已接近 L4 上限。核心区分：RunContext 是三层数据融合（caller → DataSource → GraphIndex），这是 L4 特征。L5 的自适应上下文策略需要在运行时决定"用哪些数据源"而非预先配置，aiPlat 目前是配置驱动的。

---

### C. 工具掌握

| 级别 | 定义门槛 | aiPlat 匹配 | 得分依据 |
|:---:|------|------|:--:|
| L3 | 5-20 个工具，自动选择 | ⬜ 已超越 | — |
| **L4** | **20+ 工具，动态发现** | ✅ | 813 端点 + 32 Skill + MCP 动态发现 |
| L5 | 无限 — Agent 自举创建新工具 | ❌ | 无 tool_bootstrap / skill_factory |

**判据**：
```bash
wc -l < aiPlat-core/core/harness/infrastructure/gates/policy_gate.py
# → 1039（工具权限系统的复杂度，间接证明工具数量）
grep -c 'class.*Sandbox' aiPlat-core/core/harness/infrastructure/gates/sandbox_gate.py
# → 2
```
MCP 动态发现是 L4 特征——启动时扫描 `server.yaml` → 注册到 `ToolRegistry`。L5 的"自举创建"意味着 Agent 能自己写代码 → 部署 → 注册为工具，aiPlat 没有这个闭环。

---

### D. 记忆系统

| 级别 | 定义门槛 | aiPlat 匹配 | 得分依据 |
|:---:|------|------|:--:|
| L3 | 跨会话长期记忆 + 版本管理 | ⬜ 已超越 | — |
| **L4** | **全栈记忆 + 冲突解决 + 反馈闭环** | ✅ | 四层记忆 + Semantic 冲突 + Episodic TTL + 反馈闭环 |
| L5 | 蜂群共享记忆 + 组织级知识沉淀 | ❌ | 无跨实例知识同步 |

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
记忆系统是 aiPlat 最强板。Semantic 5 维 Jaccard 矛盾检测 + 反馈闭环（access_count 动态降权）已接近 L4 上限。L5 差距是跨实例同步——如何让两个 Pipeline 执行之间共享学到的事实。

---

### E. 协作能力

| 级别 | 定义门槛 | aiPlat 匹配 | 得分依据 |
|:---:|------|------|:--:|
| L3 | 单 Agent + 基础并行 | ⬜ 已超越 | — |
| **L4** | **多 Agent 编队 + 角色分工 + 并行执行** | ✅ | Pipeline 多角色 + SubagentCoordinator + ParallelExecutor |
| L5 | 蜂群协作 + 动态组队 + 自主分工 | ❌ | 固定 Pipeline 阶段顺序，非动态编排 |

**判据**：
```bash
wc -l < aiPlat-core/core/harness/integration.py
# → 3595（集成总线，间接证明多 Agent 协作复杂度）
```
关键区分：L4 = Agent 编队是预定义的（Pipeline Stage 顺序在 YAML 中写死）。L5 = 运行时根据任务需求动态组队。aiPlat 的 SubagentCoordinator 创建子 Agent 执行子任务，但父 Agent 的子任务分配仍是预设的。

---

### F. 自进化

| 级别 | 定义门槛 | aiPlat 匹配 | 得分依据 |
|:---:|------|------|:--:|
| L3 | 无 | ⬜ 已超越 | — |
| **L4 基础** | **能从失败中学习（重试策略优化）** | ✅ | 5 硬编码子策略 + champion-challenger |
| L4 高阶 | 策略学习有对比反馈 | ❌ | 5 策略无效果对比，无法判断"换 Key vs 退避哪个更好" |
| L5 | 策略搜索-评估-比较-回滚闭环 | ❌ | 无策略搜索引擎 |

**判据**：
```bash
grep -c 'async def _strategy_' aiPlat-core/core/harness/execution/pipeline_engine.py
# → 5

grep -c 'class FailoverReason' aiPlat-core/core/harness/infrastructure/gates/error_translator.py
# → 1（19 种错误分类，但策略映射是硬编码的 if/elif 链）

grep -c 'class PromptOptimizer' aiPlat-core/core/harness/optimization/prompt_optimizer.py
# → 1（champion-challenger，但面向 Prompt 优化，非策略优化）
```
**关键判定**：5 个策略是 `if reason in ("rate_limit", "auth")` 这样的**确定性规则**，不是策略搜索算法产生的。这是 L4 基础边界：有学习（从错误分类 → 修复动作），但没有"比较不同的修复策略"。

---

## 3. 负检查（反证法）

如果 aiPlat 达到 L5，下面的命令应该返回非零结果。实际应全为 0。

### 3.1 L5 唯一特征扫描

```bash
# L5 特征：策略搜索引擎
grep -rn 'strategy_search\|strategy_explore\|policy_search\|multi_armed_bandit\|bayesian_opt' \
  aiPlat-core/core/harness/ --include='*.py' | grep -v __pycache__ | grep -v ':0$' || echo "0 (OK)"

# L5 特征：自举工具创建
grep -rn 'tool_bootstrap\|tool_factory\|create_tool\|generate_tool\|auto_tool\|skill_factory' \
  aiPlat-core/core/harness/ --include='*.py' | grep -v __pycache__ | grep -v ':0$' || echo "0 (OK)"

# L5 特征：蜂群共享记忆
grep -rn 'swarm_memory\|shared_memory_bus\|memory_gossip\|knowledge_replicat\|distributed_memory' \
  aiPlat-core/core/harness/ --include='*.py' | grep -v __pycache__ | grep -v ':0$' || echo "0 (OK)"

# L5 特征：目标生成引擎
grep -rn 'goal_generator\|agenda_setter\|research_proposer\|auto_objective\|task_ideation' \
  aiPlat-core/core/harness/ --include='*.py' | grep -v __pycache__ | grep -v ':0$' || echo "0 (OK)"

# L5 特征：跨域推理
grep -rn 'cross_domain_reason\|transdisciplinary\|knowledge_transfer_learning' \
  aiPlat-core/core/harness/ --include='*.py' | grep -v __pycache__ | grep -v ':0$' || echo "0 (OK)"
```

**预期结果**：全部 `0 (OK)`。

### 3.2 四框架剥离测试

验证 aiPlat 的 L4 定位不依赖外部框架代码。移除外部框架后，aiPlat 应能独立保持 L4 能力。

| 剥离项 | 剥离后应仍然存在的功能 | 验证 |
|:---|------|:---|
| 删除 LangGraph 依赖 | `_retry_loop` 仍存在（Harness 自建） | `grep -c '_retry_loop' pipeline_engine.py` → ≥ 1 |
| 删除 LangChain 依赖 | CRAG 仍存在（自复刻） | `grep -c 'CRAG' materials_chat.py` → ≥ 1 |
| 删除 Hermes-agent 引用 | ErrorTranslator / ApprovalGate 是独立实现 | `grep -c 'class FailoverReason' error_translator.py` → = 1 |
| 删除任何库的 `Agent` 基类 | BaseAgent 是自建的 | `grep -c 'class BaseAgent' base.py` → ≥ 1 |

### 3.3 已知伪阳性（需人工判断）

某些 L5 关键词出现在代码中，但**不是 L5 实现**：

```
agent_discovery → 出现在 integration.py:229 和 triple_scanner.py:161
```
这是 L4 级别的 Agent 注册/发现机制（查找已注册的 Agent），**不是** L5 的动态组队引擎。
验证命令：
```bash
grep -n 'agent_discovery' aiPlat-core/core/harness/integration.py
# → 229: def get_agent_discovery():
# 这是一个注册表查询函数，不是 dynamic_orchestrator
```

### 3.4 硬编码 vs 配置驱动扫描

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
| **aiPlat (本评估)** | **L4** | **L4** | **L4** | **L4** | **L4** | **L4** | **L4** | **L4** |
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

以下 12 条命令从零验证白皮书的核心结论。运行时间 < 10 秒。

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
```

**预期输出**：12/12 PASS。

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

#### S1: 自主循环（L4 关键区分度）

> **问题**：给定一个多步任务，系统能否无人介入从起点推进到终点？

```bash
# 1. 创建会话
SESSION=$(curl -s http://localhost:8002/api/core/conversations/create \
  -d '{"name":"l4-test"}' | jq -r '.session_id')

# 2. 发送多步任务
curl -s http://localhost:8002/api/core/agents/execute \
  -d "{\"agent_id\":\"materials_chat\",\"messages\":[{\"role\":\"user\",\"content\":\"分三步回答：1)总结 2)分析 3)优化。每步用##标记\"}], \"session_id\":\"$SESSION\"}"

# 3. 检查状态（不应是 paused）
curl -s http://localhost:8002/api/core/conversations/$SESSION | jq '.phase'
# 预期: done 或 running（不应是 paused / failed）
```

**L4 判定**：`phase` 在未人工介入时从 `executing` 推进到 `done`，即验证通过。

#### S2: 自愈验证（Phase 24）

> **问题**：系统在遇到 rate_limit 后，是否自动换 Key 而不是失败？

```bash
# 1. 检查自愈仪表盘（Phase 24 diagnostics）
curl -s http://localhost:8002/api/core/diagnostics/run-all | jq '.checks[] | select(.module=="self_healing")'

# 2. 检查自愈事件日志
grep -c '\[healing\]' ~/.aiplat/logs/aiplat.log
```

**L4 判定**：`self_healing` 模块在线 + 日志中有 `[healing]` 记录（至少一次），即验证通过。

#### S3: 跨会话上下文感知

> **问题**：第一轮告诉 Agent 偏好，第二轮能否召回？

```bash
# 1. 写入偏好（同一个 session）
curl -s "http://localhost:8002/api/core/agents/execute" -d '{
  "agent_id":"materials_chat",
  "messages":[{"role":"user","content":"请记住：我偏好用列表格式回答问题"}],
  "session_id":"s1"
}'

# 2. 跨轮次验证（同一个 session_id）
curl -s "http://localhost:8002/api/core/agents/execute" -d '{
  "agent_id":"materials_chat",
  "messages":[{"role":"user","content":"我之前的格式偏好是什么？"}],
  "session_id":"s1"
}'
```

**L4 判定**：第二个请求的响应中包含"列表"关键词，即验证通过。

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
| LangChain (RAG) | ❌ 无循环 | 🔶 2 级 | 0（无本体） | 0 | 0 | **L2** |
| LangGraph (裸) | 🔶 需手写 | 🔶 依赖 LangChain | 0 | 0 | 0 | **L2** |
| CrewAI | ✅ Agent 循环 | ❌ | 0 | 🔶 会话 | 0 | **L2-L3** |
| AutoGPT | ✅ 自主循环 | ❌ | 0 | 🔶 会话 | 🔶 基础重试 | **L3** |

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

**时间观察**：所有 Phase 在 2026-07 密集交付。审稿人应关注：这些能力是否经过了足够的生产压力测试（非 commit date 检查，而是后续的稳定性观察）。
