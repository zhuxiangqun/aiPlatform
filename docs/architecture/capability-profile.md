# 能力剖面（Capability Profile）— Agent 等级体系

> 版本: v4.0 | 更新: 2026-08 | 实施: `pipeline_engine.py::_apply_capability_profile()`

---

## 一、概述

`capability_profile` 是 `PipelineStageConfig` 的声明式字段（默认值 `"auto"`），替代原有的二进制 `execution_backend: llm/agent` 开关。

**核心原则**：引擎根据 Agent 的实际声明（`agent_type`、`required_tools`、`required_skills`）自动推断能力等级。人工可通过显式声明 `capability_profile` 覆盖自动推断。

---

## 二、等级定义

| 等级 | 能力数 | 典型场景 | 后端 | 触发条件 |
|------|:---:|------|:---:|------|
| `minimal` | ~5 | 纯对话（问-答模式） | llm | 无任何声明 |
| `standard` | ~15 | 有上下游依赖的上下文型 Agent | llm | phase + depends_on |
| `full` | ~30 | 需要工具/技能调用的 Agent | agent | tools 或 skills 非空 |
| `autonomous` | ~23 | 复杂推理 + 反思的自主 Agent | agent | agent_type in (react, tool, subagent) |

> **注**：能力计数为「注入的能力类」（每个类内部包含若干原子子能力，总计映射至 914 项核心能力中的约 40 项）。
| `collaborative` | ~43 | 多 Agent 协作的编排型 Agent | agent | agent_type == orchestrator |
| `self_evolving` | ~45 | 实时自适应 + 在线进化的 Agent | agent | 须人工显式声明 |
| `persistent` | ~47 | 跨会话持久化的长周期 Agent | agent | 须人工显式声明 |

### 每等级注入的能力集

| 能力 | minimal | standard | full | autonomous | collaborative | self_evolving | persistent |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Domain 上下文注入 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| prompt_loader 模板 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Pipeline 产物上下文 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| QualityBus 评分 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SKILL.md SOP 加载 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Memory.build_context()（四层记忆） | | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 5 级上下文压缩 | | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CLAUDE.md 架构规则注入 | | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Boundary Rule 注入 | | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| trace_id / span_id 观测 | | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Metrics P50/P95/P99 | | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Circuit Breaker 熔断 | | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| PolicyGate 策略门 | | | ✅ | ✅ | ✅ | ✅ | ✅ |
| PII 检测 + 脱敏 | | | ✅ | ✅ | ✅ | ✅ | ✅ |
| Injection Guard | | | ✅ | ✅ | ✅ | ✅ | ✅ |
| ReActLoop 多步推理 | | | ✅ | ✅ | ✅ | ✅ | ✅ |
| sys_tool_call（21 工具） | | | ✅ | ✅ | ✅ | ✅ | ✅ |
| sys_skill_call（53 技能） | | | ✅ | ✅ | ✅ | ✅ | ✅ |
| Hook 链（PRE/POST） | | | ✅ | ✅ | ✅ | ✅ | ✅ |
| SECI 知识螺旋 | | | ✅ | ✅ | ✅ | ✅ | ✅ |
| Feedback 记录 | | | ✅ | ✅ | ✅ | ✅ | ✅ |
| Token 预算管理（max_steps=10, budget=30000） | | | ✅ | ✅ | ✅ | ✅ | ✅ |
| Error Retry 指数退避 | | | ✅ | ✅ | ✅ | ✅ | ✅ |
| TaskSkills 晶体化 | | | | ✅ | ✅ | ✅ | ✅ |
| Reflection 自省循环 | | | | ✅ | ✅ | ✅ | ✅ |
| SubagentCoordinator（多 Agent 委派） | | | | | ✅ | ✅ | ✅ |
| AgentMessageBus（DEBATE/VOTE） | | | | | ✅ | ✅ | ✅ |
| 工具调用前理由输出（PRE_TOOL_RATIONALE） | | | | | ✅ | ✅ | ✅ |
| PolicyGate 自适应风险评分 | | | | | ✅ | ✅ | ✅ |
| OnlineEvolution（实时增量进化） | | | | | | ✅ | ✅ |
| 跨会话智能恢复（resume_from_checkpoint） | | | | | | | ✅ |

---

## 三、自动推断规则

引擎在 `PipelineEngine._infer_profile_from_stage(stage)` 中按以下优先级逐条检查，**命中即停**：

```
1. agent_type == "orchestrator" 或 pipeline_mode == "orchestrator"
   → "collaborative"

2. agent_type in ("react", "tool", "subagent")
   → "autonomous"

3. required_tools 非空 或 required_skills 非空
   → "full"

4. hitl == true 或 generate_test_plan == true
   → "full"

5. phase 非空 且 depends_on 非空
   → "standard"

6. 以上都不满足
   → "minimal"
```

> **注意**：`self_evolving` 和 `persistent` 等级**不包含在自动推断规则中**。因为它们的触发依赖运行时上下文（进化间隔、会话时长）而非 Agent 静态声明。如须启用，须在 Stage 配置中**显式声明** `capability_profile: self_evolving` 或 `capability_profile: persistent`。

### 人工覆盖

在 AGENT.md 或团队 YAML 中显式声明 `capability_profile`，引擎将跳过自动推断：

```yaml
# AGENT.md frontmatter
capability_profile: full   # 强制降级（如 react Agent 不需要 Reflection）
```

```yaml
# ~/.aiplat/teams/default.yaml
stages:
  - agent_id: pm_agent
    capability_profile: autonomous  # 强制升级（但不会超出 Agent 自身能力）
```

---

## 四、全系统 Agent 等级分布（57 个）

生成时间: 2026-08 | 生成方法: `_infer_profile_from_stage()` 自动推断

### autonomous（29 个）

> 触发条件: `agent_type` in (`react`, `tool`, `subagent`)
> 能力: ~23 能力类

| Agent | 类型 | 工具数 | 技能数 | 描述 |
|------|:---:|:---:|:---:|------|
| agent_designer | react | 8 | 12 | Agent 设计师 |
| autoreview_reviewer | react | 3 | 4 | 自动审查员 |
| backend_developer | react | 2 | 6 | 后端开发工程师 |
| bench_graph_agent | react | 5 | 9 | Graph Bench Agent |
| content_pipeline | react | 2 | 0 | 内容管线 |
| e2e_测试 | react | 3 | 5 | E2E 测试 |
| factory_agent | react | 5 | 9 | 应用工厂编排器 |
| frontend_engineer | react | 2 | 6 | 前端工程师 |
| metadata_agent | react | 3 | 6 | 视频信息Agent |
| newsletter_research | react | 2 | 0 | Newsletter 研究 |
| orchestrator_agent | react | 3 | 6 | 视频解析协调助手 |
| paper_monitor | react | 1 | 0 | 论文监控 |
| parser_agent | react | 3 | 6 | 视频解析执行助手 |
| programmer_agent | react | 3 | 6 | 程序员 |
| scaffold_agent | react | 2 | 5 | 工程脚手架生成 |
| site_tester | react | 1 | 3 | 全站自动化测试 |
| subscriber_notify | react | 1 | 0 | 新订阅通知 |
| test_executor | react | 3 | 4 | 测试执行器 |
| test_report_orchestrator | react | 1 | 0 | 测试报告修复编排器 |
| video_analysis_agent | react | 3 | 7 | 视频分析助手 |
| video_processing_agent | react | 3 | 6 | 视频处理Agent |
| 标书助手 | react | 0 | 0 | 标书助手 |
| 浏览器自动化 | react | 2 | 4 | 浏览器自动化 |
| 自动调研助手 | react | 3 | 9 | 自动调研助手 |
| debugger | subagent | 3 | 4 | 代码调试专家，可修改但不能创建新文件 |
| documentation-writer | subagent | 2 | 3 | 文档编写专家 |
| performance-analyzer | subagent | 4 | 0 | 性能分析专家 |
| secure-reviewer | subagent | 2 | 3 | 安全审计专家，只读审查，不能修改任何文件 |
| tool_agent | tool | 0 | 5 | 工具调用器 |

### full（26 个）

> 触发条件: `required_tools` 或 `required_skills` 非空
> 能力: ~30 项

| Agent | 类型 | 工具数 | 技能数 | 描述 |
|------|:---:|:---:|:---:|------|
| agent_engineer | conversational | 2 | 4 | Agent 工程师 |
| architect_agent | conversational | 2 | 6 | 系统架构师 |
| auth_agent | conversational | 2 | 5 | 用户认证助手 |
| eval_engineer | conversational | 5 | 9 | 评估工程师 |
| fde_business_analyst | conversational | 2 | 4 | FDE业务分析师 |
| fde_delivery_engineer | conversational | 3 | 6 | FDE交付工程师 |
| fde_delivery_manager | conversational | 2 | 5 | FDE交付经理 |
| fde_solution_architect | conversational | 3 | 4 | FDE方案架构师 |
| frontend_developer | conversational | 2 | 5 | 前端程序员 |
| hermes_agent | conversational | 2 | 0 | hermes_agent |
| history_agent | conversational | 2 | 5 | 历史记录Agent |
| meta_agent | conversational | 3 | 0 | 元优化器 |
| pm_agent | conversational | 0 | 2 | 产品经理 |
| qa_agent | conversational | 3 | 6 | 测试经理 |
| 政务AI落地协调员 | conversational | 0 | 5 | FDE-政务落地诊断 |
| 智能客服 | conversational | 1 | 2 | 智能客服 |
| advisor_agent | pure_agent | 1 | 1 | 🔍顾问Agent |
| employee_agent | pure_agent | 1 | 1 | ⚡员工Agent |
| guard_agent | pure_agent | 1 | 1 | 🛡️保安Agent |
| competitor_monitor | rag | 3 | 2 | 竞品监控 |
| mychatbot | rag | 2 | 3 | MyChatBot |
| materials_chat | materials_chat | 0 | 4 | RAG 知识库助手 |
| operator_agent | operator | 0 | 6 | operator_agent |
| plan_agent | plan | 0 | 4 | 任务规划器 |
| planning_agent | plan | 2 | 5 | 架构规划师 |
| 代码审核 | review | 1 | 3 | 代码审核 |

### minimal（2 个）

> 触发条件: 无 tools、无 skills、无 phase+depends_on
> 能力: ~5 项

| Agent | 类型 | 工具数 | 技能数 | 描述 |
|------|:---:|:---:|:---:|------|
| memory_os | conversational | 0 | 0 | memory_os |
| ontology_reasoner | conversational | 0 | 0 | ontology_reasoner |

> **Agent 类型说明**：`conversational`、`pure_agent`、`operator`、`materials_chat`、`rag`、`plan`、`review` 等类型在推断逻辑中**均不属于** `react/tool/subagent` 集合，因此不会自动获得 `autonomous` 等级。其中 `pure_agent` 是 `conversational` 的受限变体（最小工具集），引擎在实际调度中通过 `_CONVERSATIONAL_AGENT_TYPES` 集合统一处理 — 当 `execution_backend: agent` 时均走 StageRunner→ReActLoop 路径。

### 未激活等级

| 等级 | 原因 |
|------|------|
| `collaborative` | 无 Agent 声明 `agent_type: orchestrator` 或 `pipeline_mode: orchestrator` |
| `standard` | 无 Agent 同时满足「phase 非空 + depends_on 非空」但「tools 和 skills 均为空」（所有有依赖的 Agent 都声明了 tools 或 skills） |
| `self_evolving` | 须人工显式声明，当前无 Agent 启用 |
| `persistent` | 须人工显式声明，当前无 Agent 启用 |

---

## 五、如何检查 Agent 的当前等级

### 方法 1：查询运行日志

Pipeline 启动时，`_apply_capability_profile()` 会输出 DEBUG 日志：

```bash
grep capability_profile ~/.aiplat/logs/server.log | tail -20
# capability_profile=full backend=agent
# capability_profile=autonomous backend=agent
```

### 方法 2：Python 脚本

```python
from core.harness.execution.pipeline_engine import PipelineEngine

# 模拟 Agent 声明
stage = type('Stage', (), {
    'agent_type': 'react',
    'required_tools': ['search'],
    'required_skills': [],
})()

profile = PipelineEngine._infer_profile_from_stage(stage)
print(profile)  # → "autonomous"
```

### 方法 3：批量扫描全部 Agent

```bash
python3 -c "
from core.harness.execution.pipeline_engine import PipelineEngine
import os, yaml

agents_dir = os.path.expanduser('~/.aiplat/agents')
for name in sorted(os.listdir(agents_dir)):
    f = os.path.join(agents_dir, name, 'AGENT.md')
    if not os.path.isfile(f): continue
    with open(f) as fh:
        raw = fh.read()
    if raw.startswith('---'):
        parts = raw.split('---', 2)
        fm = yaml.safe_load(parts[1]) or {}
    else:
        fm = {}
    stage = type('S', (), {
        'agent_type': fm.get('agent_type', ''),
        'required_tools': fm.get('required_tools', []),
        'required_skills': fm.get('required_skills', []),
    })()
    print(f\"{name:35s} type={fm.get('agent_type','?'):15s} → {PipelineEngine._infer_profile_from_stage(stage)}\")
"
```

---

## 六、新增 Agent 时的最佳实践

1. **不要写 `capability_profile` 字段**——让引擎自动推断
2. **正确设置 `agent_type`**：
   - 需要工具调用 → `react`
   - 纯对话 → `conversational`
   - 知识检索 → `rag`
   - 多 Agent 编排 → `orchestrator`
3. **声明 `required_tools` 和 `required_skills`**——这是引擎推断的关键输入
4. **只在特殊需求时人工覆盖**——如 react Agent 不需要 Reflection，写 `capability_profile: full`

---

## 七、相关代码

| 文件 | 内容 |
|------|------|
| `core/schemas_builder.py:275` | `capability_profile` 字段定义 |
| `core/harness/execution/pipeline_engine.py:3963` | `_infer_profile_from_stage()` 静态推断 |
| `core/harness/execution/pipeline_engine.py:3991` | `_apply_capability_profile()` 能力注入 |
| `core/harness/execution/team_planner.py:331` | 编排期自动推断集成 |
| `core/engine/skills/agent_engineering/SKILL.md:104` | SOP 中 agent_type 生成规则 |
| `core/harness/infrastructure/gates/policy_gate.py:303` | `_adaptive_mode` + 风险评分 |
| `core/harness/infrastructure/hooks/online_evolution.py` | POST_LOOP 实时进化 hook |
| `core/harness/interfaces/messaging.py:28` | AgentMessageType DEBATE/VOTE |
| `scripts/benchmark_memory.py` | 记忆压缩基准测试 |
| `core/api/routers/pipeline_execution.py:387` | `POST /pipelines/runs/{id}/resume` |
| `core/services/execution_store/_base.py:354` | `get_recent_syscall_events()` — v5.0 校准数据源 |
| `core/harness/execution/pipeline_engine.py:4080` | `_calibrate_profile_from_history()` — 运行时校准 |
| `core/harness/execution/pipeline_engine.py:4215` | 校准挂载点 — `_apply_capability_profile` 尾部 |

---

## 八、v5.0：运行时剖面校准

> 版本: v5.0 | 实施: `pipeline_engine.py::_calibrate_profile_from_history()`

### 概述

v1.0-v4.0 用 Agent 的**静态声明**推断能力等级。v5.0 新增 Phase 4——用 Agent 的**运行时实际行为**对比声明，发现偏差并自动纠正。

```
📝 Phase 2 (构建):  _infer_profile_from_stage     → 静态推断（AGENT.md 声明）
⚡ Phase 3 (运行):  _apply_capability_profile      → 注入能力集
🔍 Phase 4 (校准):  _calibrate_profile_from_history → 回看历史，发现偏差
```

### 校准逻辑

数据源: `execution_store.get_recent_syscall_events(run_id, limit=50)`

| # | 条件 | 结果 |
|:---:|------|------|
| 1 | 事件数 < 10 | `insufficient_data`（冷启动保护） |
| 2 | Agent 在正常执行已声明 Skill | 容忍隐式工具调用 |
| 3 | 使用了 2+ 未声明工具 + 步数 > 3 + 零工具声明 | `upgrade_recommended → full` |
| 4 | 声明了工具但从不用 + ≥20 事件 | `downgrade_suggested` |

### 三种运行模式

| 模式 | 环境变量 | 行为 |
|------|------|------|
| `log_only` | 默认 | 只记录偏差到日志，不修改配置 |
| `auto_upgrade` | `AIPLAT_PROFILE_CALIBRATE=upgrade` | 自动升级（只升不降，最多 2 级） |
| `auto_adjust` | `AIPLAT_PROFILE_CALIBRATE=full` | 完整校准（升级 + 降级） |

### 升级幅度规则

| 当前等级 | 可升至 | 触发条件 |
|------|:---:|------|
| `minimal` | `full` | undeclared_tools >= 2 且 avg_steps > 3 |
| `standard` | `full` | 同上 |
| `full` | — | 不自动升到 `autonomous` 及以上 |

### 发布策略

| 阶段 | 模式 | 持续 | 目标 |
|:---:|------|:---:|------|
| 1 | `log_only`（默认） | 1-2 周 | 积累校准日志，验证准确性 |
| 2 | `auto_upgrade` 灰度 | 3-5 个非关键 Agent | 验证自动升级 |
| 3 | `auto_upgrade` 全量 | 持续 | 生产级自动校准 |
| 4 | `auto_adjust` 评估 | 基于数据决策 | 完整自主校准 |

### 版本演进

| 版本 | 数据源 | 判断标准 |
|:---:|------|------|
| v1.0-v4.0 | AGENT.md 静态声明 | 声明了什么 |
| **v5.0** | **执行运行时行为** | **实际做了什么** |
| v6.0 (展望) | 用户反馈 | 用户满意什么 |
