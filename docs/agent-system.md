# aiPlat Agent 系统 — 完整指南

> 最后更新: 2026-08-11 · 原理优先，细节后置 · 配置/API 见附录
> 能力等级体系详见 [capability-profile.md](architecture/capability-profile.md)

---

## 一、Agent 要解决什么问题

aiPlat 平台的核心能力通过 Agent 对外服务。Agent 不是简单的「LLM 包装器」，而是一个**具备自主推理、工具调用、记忆管理和质量评估能力的执行单元**。

一个 Agent 由三部分组成：

```
Agent = 声明(AGENT.md) + 运行时(ReActLoop) + 能力集(Skill/Tool/Memory)
```

| 部分 | 定义位置 | 作用 |
|------|------|------|
| 声明 | `~/.aiplat/agents/{id}/AGENT.md` | 我是谁、我会什么、我的限制是什么 |
| 运行时 | `pipeline_engine._run_stage_skill()` | 如何执行（单次 LLM vs ReAct 循环） |
| 能力集 | Skill/Tool/Memory/PolicyGate | 执行时能用什么（由 capability_profile 决定） |

---

## 二、Agent 的类型与能力等级

### 2.1 8 种预定义类型

引擎根据 `agent_type` 字段选择执行路径。类型列表（来自代码 `_CONVERSATIONAL_AGENT_TYPES` + `agent_type` 推断规则）：

| 类型 | 典型执行路径 | 适用场景 |
|------|------|------|
| `conversational` | `core_chat`（单次 LLM 调用） | 对话、信息收集 |
| `react` | ReActLoop（多步推理+工具调用） | 复杂任务、代码生成 |
| `rag` | ReActLoop + knowledge_retrieve | 知识检索 |
| `plan` | Plan-Execute 模式 | 任务规划 |
| `subagent` | SubagentCoordinator | 子 Agent 委派 |
| `tool` | 工具调用器 | 纯工具操作 |
| `orchestrator` | ReActLoop + SubagentCoordinator | 多 Agent 编排 |
| `materials_chat` | 6 阶段认知 RAG | 企业知识库问答 |

### 2.2 能力等级（capability_profile）

引擎根据 Agent 的静态声明自动推断能力等级。等级从低到高：

```
minimal → standard → full → autonomous → collaborative → self_evolving → persistent
```

| 等级 | 能力数 | 触发条件 |
|------|:---:|------|
| `minimal` | ~5 | 无任何声明 |
| `standard` | ~15 | phase + depends_on |
| `full` | ~30 | tools 或 skills 非空 |
| `autonomous` | ~40 | agent_type in (react, tool, subagent) |
| `collaborative` | ~43 | agent_type == orchestrator |
| `self_evolving` | ~45 | 须人工显式声明 |
| `persistent` | ~47 | 须人工显式声明 |

> 每个等级注入的完整能力清单、自动推断规则、57 个 Agent 的当前等级分布，详见 [capability-profile.md](architecture/capability-profile.md)。

---

## 三、Agent 的生命周期

```
创建(AGENT.md) → 注册(discovery) → 配置(pipeline_stage)
  → 执行(_run_stage_skill) → 观测(trace/metrics) → 进化(TaskSkills)
```

### 3.1 创建

Agent 通过编写 AGENT.md 文件创建。核心字段：

```yaml
---
name: my_agent
display_name: 我的 Agent
agent_type: react           # 决定执行路径
required_skills:            # 绑定的 Skill
  - code_generation
required_tools:             # 可用的 Tool
  - search
  - file_operations
output_artifact: code       # 产出物在 state 中的 key
phase: development           # Pipeline 阶段
scoring_dimensions:          # 质量评分维度
  - name: completeness
    weight: 0.5
---
```

AGENT.md 是 Agent 的**唯一真相源**。`team_planner._enrich_stage_from_agent()` 在 Pipeline 构建时读取它，填充 `PipelineStageConfig` 的 50+ 字段。

### 3.2 注册

Agent 放置在以下目录之一即可被引擎自动发现：

| 目录 | 扫描函数 | 用途 |
|------|------|------|
| `~/.aiplat/agents/{id}/AGENT.md` | `list_available_agents()` | 用户自定义 Agent |
| `core/engine/agents/{id}/AGENT.md` | 同上 | 引擎内置 Agent |

引擎启动时通过 `team_planner.list_available_agents()` 扫描所有 AGENT.md 文件，构建 `AgentCatalogEntry` 列表（含 agent_id、agent_type、phase、skills、depends_on、output_artifact）。

### 3.3 执行

Pipeline 运行时，引擎按以下顺序执行每个 stage：

```
1. _enrich_stage_from_agent()    ← 读取 AGENT.md 填充 stage 配置
2. _apply_capability_profile()   ← 根据声明自动推断能力等级
3. _calibrate_profile_from_history()  ← v5.0 运行时校准
4. _run_stage_skill()
   ├── execution_backend == "llm"   → sys_llm_generate() 单次调用
   └── execution_backend == "agent" → StageRunner.run() → ReActLoop
        ├── Memory.build_context()  四层记忆注入
        ├── CLAUDE.md 规则注入
        ├── sys_tool_call / sys_skill_call  工具与技能调用
        ├── Hook 链 (PRE_REASONING→POST_LOOP)
        ├── PolicyGate 权限检查
        └── SECI 知识原子转化
```

### 3.4 观测

每次 Agent 执行产生完整的可观测数据：

| 数据 | 记录位置 | 用途 |
|------|------|------|
| trace_id / span_id | syscall_events 表 | 全链路追踪 |
| P50/P95 延迟 | MetricsCollector | 性能监控 |
| 工具/技能调用记录 | syscall_events 表 | 运行时剖面校准 |
| HITL 审批状态 | pipeline_runs 表 | 人工反馈闭环 |

### 3.5 进化

Agent 通过 `_calibrate_profile_from_history()` 持续校准自身的能力等级。此外：

- **TaskSkills 晶体化**：Agent 执行 pipeline 的 pass_rate ≥ 85% 时，其执行模式自动注册为可复用的 TaskSkill
- **SECI 知识螺旋**：每次 Agent 交互通过 POST_LOOP hook 自动转化为知识原子
- **OnlineEvolution**：Pipeline 产生 ≥3 个知识原子或 HITL 连续被拒 3 次时，触发实时进化

---

## 四、Agent 如何执行

### 4.1 两种执行后端

引擎根据 `capability_profile` 自动选择执行后端：

| 后端 | 适用等级 | 执行方式 | 能力 |
|------|:---:|------|------|
| `llm` | minimal / standard | `sys_llm_generate` 单次调用 | SOP + Pipeline 上下文 + Domain 路由 |
| `agent` | full 及以上 | `StageRunner.run()` → ReActLoop | 全部能力（工具/技能/记忆/Hook/PolicyGate/SECI） |

`execution_backend` 字段**不可从 AGENT.md 读取**（架构安全规则，防止 Agent 自定执行路径）。它由 `capability_profile` 自动决定或由团队 YAML 显式声明。

### 4.2 ReActLoop 执行流程

```
Reason（推理）
  │
  ├── Memory.build_context()  注入四层记忆
  ├── CLAUDE.md 规则注入
  ├── HookPhase.PRE_REASONING  触发
  │
  ▼
Act（行动）
  │
  ├── sys_tool_call → PolicyGate → 执行工具 → POST_TOOL_USE
  ├── sys_skill_call → PolicyGate → 执行技能 → POST_SKILL_USE
  │
  ▼
Observe（观察）
  │
  ├── Tool/Skill 返回结果
  ├── HallucinationTracker 检测不忠实答案
  ├── HookPhase.POST_OBSERVE 触发
  │
  ▼
Loop（循环——回到 Reason）
  │
  ├── max_steps 限制（默认 10）
  ├── tokens_budget 限制（默认 30000）
  └── 满足完成条件或超限 → 退出
       │
       ▼
  HookPhase.POST_LOOP
  ├── Memory.save_interaction()  持久化
  ├── SECI hook  知识原子转化
  └── Feedback 记录
```

### 4.3 关键安全机制

| 机制 | 触发点 | 作用 |
|------|------|------|
| PolicyGate | 所有 sys_tool_call / sys_skill_call | 权限检查（拒绝率过高→动态升级为 APPROVAL_REQUIRED） |
| PII Detection | sys_llm_generate | 自动脱敏用户输入中的手机/身份证/邮箱 |
| Injection Guard | sys_llm_generate | 检测提示词注入攻击（14 条正则规则） |
| Circuit Breaker | sys_llm_generate | 5 次连续失败→断路 30s |

---

## 五、如何创建、配置与生成 Agent

### 5.1 手动创建

在 `~/.aiplat/agents/{agent_id}/` 下创建 AGENT.md，包含 frontmatter + SOP。Agent 放置后立即可被 `list_available_agents()` 发现，无需重启。

### 5.2 通过 Builder 生成

Builder 管线（PM→架构师→AgentEngineer→前端→QA）可通过 `agent_engineering` Skill 自动生成 Agent：

```
用户需求 → PM 生成 PRD → 架构师设计 → AgentEngineer 调用 agent_engineering
  → 输出 AGENT.md + SKILL.md × N → 自动注册
```

生成的 Agent 自动继承：
- 知识图谱（DomainRouter 域上下文注入）
- 四层记忆（Working/Episodic/Semantic/TaskSkill）
- 模型层级路由（T1-T5 自适应选择）
- QualityBus 评分
- PolicyGate 权限

### 5.3 配置团队

Agent 通过团队 YAML (`~/.aiplat/teams/*.yaml`) 组装为 Pipeline：

```yaml
team_name: "Agent 研发团队（默认）"
stages:
  - agent_id: pm_agent
    order: 0
    skill_name: requirement_analysis
  - agent_id: architect_agent
    skill_name: architecture_design
  - agent_id: agent_engineer
    skill_name: agent_engineering
```

团队 YAML 中 **不需要写 `execution_backend` 或 `capability_profile`**——引擎根据 Agent 的 AGENT.md 声明自动推断。

---

## 六、Subagent 协作机制

### 6.1 什么是 Subagent

Subagent 是**主 Agent 派生的轻量子 Agent**，具有受限的工具权限和独立的执行上下文。适用于：

- 安全审查（只读 Subagent 审查代码，不能修改文件）
- 并行处理（同时执行多个独立子任务）
- 任务委派（主 Agent 协调，Subagent 执行细节）

### 6.2 执行策略

`SubagentCoordinator` 支持 3 种策略：

| 策略 | 行为 | 适用场景 |
|------|------|------|
| `SEQUENTIAL` | 逐个执行 | 子任务有依赖 |
| `PARALLEL` | 并发执行 | 独立子任务 |
| `COORDINATED` | 协调执行（共享中间结果） | 需要汇总的复杂任务 |

### 6.3 摘要原则

Subagent 与父 Agent 之间遵循 **协议约束**（CLAODE.md §5.26）：

| 规则 | 说明 |
|------|------|
| ✅ 必须返回 | 成功/失败标志、关键结果、源文件数量、错误数量 |
| ❌ 禁止返回 | 完整 tool 调用链、中间推理步骤、大段代码 |

**这是 Subagent 的协议责任**——Subagent 的 AGENT.md SOP 应设计为只输出结论，不输出工具调用内部日志。引擎提供 4 层降级摘要作为兜底防线（`_summarize_output()`）：

| 层级 | 策略 | 可靠性 |
|:---:|------|:---:|
| 0 | **程序化正则过滤** | ✅ 确定性——强制移除工具调用链、代码块、推理标记 |
| 1 | 5 级上下文压缩 | ✅ 确定性——保留关键语义，丢弃冗余 |
| 2 | LLM 轻量格式摘要 | ✅ 可靠——输入已被第 0 层清理，LLM 只需提取结论 |
| 3 | 安全截断 | ✅ 确定性——在句子边界断开 |

> 实现: `subagent/coordinator.py:267` — `_summarize_output()` + `_safe_truncate()`

### 6.4 Agent 间通信

Agent 之间通过 `AgentMessageBus` 通信，支持 9 种消息类型：

| 类型 | 方向 | 用途 |
|------|------|------|
| `TASK_ASSIGN` | 主→子 | 委派任务 |
| `RESULT` | 子→主 | 返回结果 |
| `ERROR` | 子→主 | 错误报告 |
| `PROGRESS_UPDATE` | 子→主 | 进度通知 |
| `REQUEST/RESPONSE` | 双向 | 点对点请求 |
| `CANCEL` | 双向 | 取消任务 |
| `DEBATE` | 双向 | 对等辩论（v3.0 预留） |
| `VOTE` | 双向 | 投票决策（v3.0 预留） |

---

## 七、全系统 Agent 概览（57 个）

### 7.1 按能力等级分布

| 等级 | 数量 | 典型 Agent |
|------|:---:|------|
| `autonomous` | 29 | programmer_agent、backend_developer、video_analysis_agent |
| `full` | 26 | pm_agent、architect_agent、agent_engineer、qa_agent |
| `minimal` | 2 | memory_os、ontology_reasoner |

### 7.2 autonomous 等级（29 个，react/tool/subagent 类型）

| Agent | 类型 | 描述 |
|------|:---:|------|
| agent_designer | react | Agent 设计师 — 生成 AGENT.md 和 SKILL.md |
| autoreview_reviewer | react | 自动审查员 — 代码质量/安全/风格检查 |
| backend_developer | react | 后端开发 — 根据 api_contracts 生成 API 路由 |
| bench_graph_agent | react | 基准测试 Agent — 系统图工具 |
| content_pipeline | react | 内容管线 — 热点搜索 + 选题生成 |
| debugger | subagent | 代码调试 — 可修改不能创建文件 |
| documentation-writer | subagent | 文档编写 |
| e2e_测试 | react | E2E 测试自动生成 |
| factory_agent | react | 应用工厂编排器 — 全自动应用构建 |
| frontend_engineer | react | 前端工程师 — 根据 api_contracts 生成前端代码 |
| metadata_agent | react | 视频信息 Agent |
| newsletter_research | react | Newsletter 研究 |
| orchestrator_agent | react | 视频解析协调助手 |
| paper_monitor | react | 论文监控 — arXiv 搜索 |
| parser_agent | react | 视频解析执行 |
| performance-analyzer | subagent | 性能分析 |
| programmer_agent | react | 程序员 — 根据 PRD+架构产出代码 |
| scaffold_agent | react | 工程脚手架生成 |
| secure-reviewer | subagent | 安全审计 — 只读审查 |
| site_tester | react | 全站自动化测试 |
| subscriber_notify | react | 新订阅通知 |
| test_executor | react | 测试执行器 — 运行用例生成报告 |
| test_report_orchestrator | react | 测试报告修复编排器 |
| tool_agent | tool | 工具调用器 |
| video_analysis_agent | react | 视频分析助手 |
| video_processing_agent | react | 视频处理 Agent |
| 标书助手 | react | 围标串标检测 |
| 浏览器自动化 | react | 浏览器自动化 Agent |
| 自动调研助手 | react | 多平台调研 + 研究报告 |

### 7.3 full 等级（26 个）

| Agent | 类型 | 描述 |
|------|:---:|------|
| agent_engineer | conversational | Agent 工程师 — 生成 Agent 应用 |
| architect_agent | conversational | 系统架构师 — PRD→架构设计 |
| auth_agent | conversational | 用户认证助手 |
| eval_engineer | conversational | 评估工程师 — 生成评估代码 |
| fde_business_analyst | conversational | FDE 业务分析师 |
| fde_delivery_engineer | conversational | FDE 交付工程师 |
| fde_delivery_manager | conversational | FDE 交付经理 |
| fde_solution_architect | conversational | FDE 方案架构师 |
| frontend_developer | conversational | 前端程序员 |
| hermes_agent | conversational | Hermes Agent |
| history_agent | conversational | 历史记录 Agent |
| materials_chat | materials_chat | RAG 知识库助手 |
| meta_agent | conversational | 元优化器 |
| mychatbot | rag | Q&A 助手 |
| operator_agent | operator | 运维决策助手 |
| plan_agent | plan | 任务规划器 |
| planning_agent | plan | 架构规划师 — PRD→团队配置 |
| pm_agent | conversational | 产品经理 — 需求收集→PRD |
| qa_agent | conversational | 测试经理 — 测试用例设计 |
| 代码审核 | review | 代码品质分析 |
| 政务AI落地协调员 | conversational | FDE-政务落地诊断 |
| 智能客服 | conversational | 智能客服机器人 |

### 7.4 minimal 等级（2 个）

| Agent | 类型 | 描述 |
|------|:---:|------|
| memory_os | conversational | Memory OS — 记忆审计/调和/遗忘 |
| ontology_reasoner | conversational | 本体推理 — 多跳推理风险/机会/异常 |

> 完整的能力分布（含工具数、技能数）和等级详情见 [capability-profile.md](architecture/capability-profile.md) §四。

---

## 八、运维与诊断

### 8.1 Agent 健康检查

| 检查项 | 工具 | 说明 |
|------|------|------|
| Agent 产物质量 | `check_artifact_quality()` | 抽样 pipeline 产出物运行已有校验器 |
| Agent 等级偏差 | `check_ontology_health()` | 孤儿 Agent/Skill 检测 |
| 运行时校准 | `_calibrate_profile_from_history()` | 声明 vs 行为偏差自动纠正 |
| HITL 反馈 | `check_human_feedback()` | 审批率异常检测（3σ 阈值） |

### 8.2 常用命令

```bash
# 查看某个 Agent 的当前能力等级（模拟推断）
python3 -c "
from core.harness.execution.pipeline_engine import PipelineEngine
stage = type('S',(),{'agent_type':'react','required_tools':['search']})()
print(PipelineEngine._infer_profile_from_stage(stage))
"

# 批量查看所有 Agent 的等级
for f in ~/.aiplat/agents/*/AGENT.md; do
  name=$(basename $(dirname $f))
  type=$(grep agent_type: $f | awk '{print $2}')
  echo "$name ($type)"
done
```

---

## 九、常见问题

**Q: Agent 和 Skill 的区别是什么？**
A: Agent 是「谁来做」——负责编排和决策。Skill 是「怎么做」——负责执行具体的操作步骤。一个 Agent 可以调用多个 Skill，一个 Skill 可以被多个 Agent 使用。

**Q: 如何选择 agent_type？**
A: 需要工具调用→`react`，纯对话→`conversational`，知识检索→`rag`，多 Agent 编排→`orchestrator`。**不需要手写 `execution_backend` 或 `capability_profile`**——引擎自动根据声明推断。

**Q: 如何升级 Agent 的能力？**
A: 在 AGENT.md 中增加 `required_tools` 和 `required_skills` 声明。引擎在下次执行时自动推断更高的能力等级。或直接显式声明 `capability_profile: autonomous` 覆盖自动推断。

**Q: Subagent 和主 Agent 的区别？**
A: Subagent 是轻量级 Agent，具有受限权限、独立上下文、摘要返回。适用于安全审查（只读）、并行处理、任务委派。

**Q: 如何查看 Agent 使用哪些核心能力？**
A: 引擎会在 DEBUG 日志中输出 `capability_profile=xxx backend=xxx`。或使用 [capability-profile.md](architecture/capability-profile.md) §五 的批量扫描脚本。

---

## 附录 A：Agent 执行流程时序

```
1. Pipeline 启动
2. team_planner._enrich_stage_from_agent()
   └── 读取 AGENT.md → 填充 PipelineStageConfig
3. pipeline_engine._run_stage_skill()
   ├── _apply_capability_profile()
   │   └── _infer_profile_from_stage()  自动推断等级
   ├── _calibrate_profile_from_history()  v5.0 校准
   ├── execution_backend == "llm" ?
   │   ├── YES → sys_llm_generate(SOP + context)
   │   └── NO  → StageRunner.run() → ReActLoop
   └── 输出 → state[output_artifact]
4. Pipeline 继续下一个 stage
```

## 附录 B：相关文档

| 文档 | 内容 |
|------|------|
| [capability-profile.md](architecture/capability-profile.md) | 7 级能力剖面定义、推断规则、57 Agent 完整分布 |
| [subagent.md](agents/subagent.md) | Subagent 架构设计详述 |
| [knowledge-system.md](knowledge-system.md) | 知识系统完整指南（含本体/TripleStore/Agent 在知识图中的角色） |
| [ai-app-factory.md](design/ai-app-factory.md) | Builder 管线（如何生成应用） |
