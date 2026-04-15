# 架构实现状态

> 本文档是 aiPlat-core 各子系统实现状态的**唯一真相来源**。
> 最后更新: 2026-04-15（Phase 7 + Phase 8 全部完成）

## 状态标记说明

| 标记 | 含义 |
|------|------|
| ✅ 已实现 | 代码存在且功能可用 |
| ⚠️ 部分实现 | 代码存在但有已知问题，不能端到端运行 |
| 🔧 结构存在 | 代码框架存在但关键桥接缺失，无法实际运行 |
| ❌ 未实现 | 代码不存在或仅是接口定义（ABC） |
| 📝 仅文档 | 文档描述了功能但无对应代码 |
| 🩹 已修复 | 之前断裂，现已桥接 |

---

## 架构决策记录

> 以下决策由 2026-04-15 架构审计后做出，影响后续所有实现。

### 决策 1：命名空间统一

**决策**：所有 Skill/Agent 的 `id` 字段即为语义名称（如 `text_generation`、`react_agent`），不再使用 UUID 风格 ID。Manager 和 Registry 共享同一键空间。

**影响**：
- 种子数据 ID 统一：`skill-planning` → `task_planning`，`agent-react-01` → `react_agent` 等
- `SkillManager.create_skill()` 和 `AgentManager.create_agent()` 生成 ID 时使用名称化为下划线格式
- `SkillExecutor.execute(skill_id)` 和 `AgentRegistry.get(agent_id)` 使用同一键

### 决策 2：Agent 执行路径

**决策**：方案A — Harness Loop 驱动。所有 Agent 子类不再 override `execute()`，通过 `BaseAgent.execute() → self._loop.run(state, config)` 执行。

**影响**：
- ReActAgent 的自建推理循环迁移到 ReActLoop._reason/_act/_observe
- PlanExecuteAgent 的自建规划逻辑迁移到 PlanExecuteLoop
- ConversationalAgent 通过 Loop + Hook 实现对话
- BaseAgent._loop 不再是死代码

### 决策 3：LangGraph 角色

**决策**：修复集成，LangGraph StateGraph 作为图执行主路径。

**影响**：
- AgentState 从 @dataclass 改为 TypedDict
- 修复 `from langgraph.nodes import Node` 错误 import
- `_run_fallback` 仍保留作为降级路径

### 决策 4：Manager → Registry 桥接

**决策**：`SkillManager.create_skill()` 调用 `_bridge_to_registry()` 将 SkillInfo 同步注册到 SkillRegistry。`AgentManager.create_agent()` 同理。

**影响**：
- CRUD 创建的 Skill/Agent 立即可执行
- 种子数据在 `_seed_data()` 结尾时也桥接到 Registry

---

## 核心断裂点修复进度

### 断裂 1：管理层 ↔ 执行层 — 🩹 已修复

```
SkillManager (CRUD)  → _bridge_to_registry() →  SkillRegistry (执行)
AgentManager (CRUD)  → _bridge_to_registry() →  AgentRegistry (执行)
```

| 操作 | 管理层 | 执行层 | 桥接？ |
|------|--------|--------|--------|
| 创建 Skill | SkillManager.create_skill() → SkillInfo | SkillRegistry 自动注册 BaseSkill | ✅ |
| 创建 Agent | AgentManager.create_agent() → AgentInfo | AgentRegistry 自动注册 Agent | ✅ |
| 种子数据 Skill | SkillManager._seed_data() | SkillRegistry.seed_data() 创真实实例 + bridge | ✅ |
| 种子数据 Agent | AgentManager._seed_data() | AgentRegistry 通过 bridge 注册 | ✅ |
| 发现 Skill | SkillDiscovery 扫描 SKILL.md | 注册为 _GenericSkill 到 Registry | ✅ |
| 发现 Agent | AgentDiscovery 扫描 AGENT.md | 注册为 Agent 到 Registry | ✅ |
| 执行 Skill | SkillExecutor 查 SkillRegistry | Registry 有真实 BaseSkill 实例 | ✅ |
| 执行 Agent | server.py 查 AgentRegistry | Registry 有真实 Agent 实例 | ✅ |

### 断裂 2：Harness Loop ↔ Agent — 🩹 已修复

ReActAgent 和 PlanExecuteAgent 的 `execute()` 委托给 `BaseAgent.execute()`，后者在运行前将 model/tools/skills 注入 loop 并调用 `self._loop.run()`。ConversationalAgent 保留 override（单次 LLM 调用不需要 Loop）。

### 断裂 3：SkillContext.tools 注入 — 🩹 已修复

`SkillExecutor._execute_inline()` 从 skill 的 `config.metadata['tools']` 提取工具名注入 `SkillContext.tools`；`execute_skill` endpoint 创建含 tools 的 `SkillContext`。

---

## 子系统状态

### Skill 系统

| 组件 | 状态 | 说明 |
|------|------|------|
| SkillManager (CRUD) | ✅ | 创建/读取/更新/删除/启用/禁用 都可用 |
| SkillRegistry | ✅ | seed_data() 创建真实 BaseSkill 实例；Manager → Registry 桥接完成 |
| SkillExecutor | ✅ | Registry 有实例后可执行 Skill |
| BaseSkill 子类 | ⚠️ | TextGeneration/CodeGeneration/DataAnalysis 可用，但 `_model=None` 需注入 |
| _GenericSkill | ✅ | 新增：通用 Skill 实现，用于无专用子类的 Skill |
| SkillDiscovery → Registry | ✅ | lifespan 中自动注册发现结果 |
| SkillManager.execute_skill() | ✅ | 调用 SkillExecutor.execute() 并更新审计记录 |
| Skill 版本管理 | ✅ | create_version/rollback_version/get_versions 端点均可用 |
| Skill Fork Mode | ✅ | _execute_fork() 通过 ConversationalAgent 子 Agent 执行 |
| Skill 权限控制 | ✅ | execute_skill endpoint 调用 PermissionManager.check_permission() |

### Agent 系统

| 组件 | 状态 | 说明 |
|------|------|------|
| AgentManager (CRUD) | ✅ | 完整 CRUD + 技能/工具绑定 + → Registry 桥接 |
| AgentRegistry | ✅ | 通过 Manager bridge 填充真实 Agent 实例 |
| AgentDiscovery → Registry | ✅ | lifespan 中自动注册发现结果 |
| ReActAgent | ✅ | 委托 super().execute()（Harness Loop 驱动） |
| PlanExecuteAgent | ✅ | 委托 super().execute()（Harness Loop 驱动） |
| ConversationalAgent | ✅ | 保留 execute() override（对话模式不需要 Loop，直接调 model） |
| RAGAgent | ✅ | import 修复 + _model 修复 + 工厂映射 rag→RAGAgent |
| MultiAgent | ✅ | 使用 Harness Coordination Patterns（Pipeline/FanOut/Expert/Producer/Supervisor） |
| BaseAgent._loop | ✅ | execute() 注入 model/tools/skills 到 loop 后运行 |

### Tool 系统

| 组件 | 状态 | 说明 |
|------|------|------|
| ToolRegistry | ✅ | 全局单例，启动注册 3 个 tool |
| CalculatorTool | ✅ | 真实可用 |
| SearchTool | ✅ | 真实可用（DuckDuckGo） |
| FileOperationsTool | ❌ | 桩 |
| CodeExecutionTool | ❌ | 桩（需要沙箱） |
| DatabaseTool | ❌ | 桩（需要数据库驱动） |
| BrowserTool | ❌ | 桩（需要 Playwright） |
| WebFetchTool | ✅ | 真实实现（aiohttp），server.py lifespan 注册 |
| HTTPClientTool | ✅ | 真实实现（aiohttp），server.py lifespan 注册 |
| Agent 版本管理 | ✅ | create_version/rollback_version/get_versions 端点均可用 |
| PermissionManager | ✅ | execute_agent 和 execute_skill endpoint 均调用 check_permission() |

### Harness 系统

| 组件 | 状态 | 说明 |
|------|------|------|
| Policy Engine | ✅ | 策略规则完整可用 |
| Memory 系统 | ✅ | 短期/工作/情景/语义四层 |
| Knowledge 检索 | ⚠️ | 可用但使用 hash 伪向量 |
| Hook 系统 | ✅ | 修复 PRE_SKILL_USE→POST_SKILL_USE Bug |
| Coordination 模式 | 🔧 | 5 种模式存在，从未被调用 |
| Convergence 检测 | ✅ | 4 种检测器可用 |
| ReActLoop | ✅ | 实现 _reason/_act/_observe 步骤；支持 ApprovalManager 注入（PRE_TOOL_USE 审批） |
| PlanExecuteLoop | ✅ | _plan() 传 messages 列表给 model；_execute() 完整实现 tool/skill/model 三层执行 |
| HeartbeatMonitor | ✅ | _start_monitor_loop 通过 asyncio.ensure_future 启动 |
| BaseAgent.execute() | ✅ | 执行前注入 model/tools/skills 到 loop |
| ReActAgent.execute() | ✅ | 委托给 super().execute()（Harness Loop 驱动） |
| PlanExecuteAgent.execute() | ✅ | 委托给 super().execute()（Harness Loop 驱动） |
| LangGraph 状态类型 | ✅ | AgentState→TypedDict；PlanningState/ReflectionState/MultiAgentState/TriAgentState→TypedDict |
| LangGraph import | ✅ | 移除错误 `from langgraph.nodes import Node` |
| AgentState 重名 | ✅ | harness/state.py AgentState→AgentLifecycleState（保留别名） |
| RAGAgent | ✅ | 修复 import bug（AgentContext）、self._llm_adapter→self._model、context.query→context.variables |
| ConversationalAgent | ⚠️ | 保留 execute() override（对话模式不需要 Loop）；直接调 model.generate() |

---

## 修复优先级（已更新 Phase 7）

| 优先级 | 修复 | 状态 | 影响 |
|--------|------|------|------|
| P0 ✅ | SkillRegistry.seed_data() 创建真实实例 | ✅ 已完成 | SkillExecutor 能找到 Skill |
| P0 ✅ | SkillManager.create_skill() → SkillRegistry 桥接 | ✅ 已完成 | CRUD 创建的 Skill 可执行 |
| P0 ✅ | AgentManager.create_agent() → AgentRegistry 桥接 | ✅ 已完成 | CRUD 创建的 Agent 可执行 |
| P0 ✅ | server.py 缺失 import | ✅ 已完成 | 执行端点不再 NameError |
| P0 ✅ | 命名空间统一 ID=name | ✅ 已完成 | Manager 和 Registry 共享键空间 |
| P0 ✅ | Discovery → Registry 自动注册 | ✅ 已完成 | 发现的组件可执行 |
| P1 ✅ | SkillExecutor 注入 tools 到 SkillContext | ✅ 已完成 | Skill 执行时能访问 Tool |
| P1 ✅ | ReActLoop PRE/POST Bug + messages 修复 | ✅ 已完成 | Loop 能正确执行 |
| P1 ✅ | LLM Adapter 注入管道 | ✅ 已完成 | Skill/Agent 能获取 model |
| P1 ✅ | LangGraph TypedDict 迁移 + import 修复 | ✅ 已完成 | StateGraph 能正确构建 |
| P1 ✅ | AgentState 重名解决 | ✅ 已完成 | 消除 state.py vs reason_node.py 命名冲突 |
| P1 ✅ | RAGAgent import + 属性名修复 | ✅ 已完成 | RAGAgent 能运行 |
| P2 ✅ | Agent Loop 委托 | ✅ 已完成 | ReActAgent/PlanExecuteAgent 委托 Loop；ConversationalAgent 保留 override（合理） |
| P2 ✅ | HeartbeatMonitor 启动 | ✅ 已完成 | _monitor_loop 通过 asyncio.ensure_future 启动 |
| P2 ✅ | PlanExecuteLoop._execute() 完整实现 | ✅ 已完成 | tool→skill→model 三层执行 |
| P2 ✅ | Agent 类型映射 | ✅ 已完成 | plan→PlanExecuteAgent, tool→ReActAgent, rag→RAGAgent |
| P2 ⏳ | 统一状态类型（AgentLifecycleState vs LoopState） | 待做 | 命名冲突已解决但职责仍分离 |
| P3 ✅ | Coordination 模式接入 MultiAgent | ✅ 已完成 | 5 种模式全部接入 MultiAgent.execute() |
| Phase 8 ✅ | SkillManager.execute_skill() 调用 SkillExecutor | ✅ 已完成 | 执行审计完整 |
| Phase 8 ✅ | 删除死代码接口（IAdapter/IRouter/IContext） | ✅ 已完成 | 3 个无用接口文件已删除 |
| Phase 8 ✅ | PermissionManager 接入执行路径 | ✅ 已完成 | agent/skill endpoint 均检查权限 |
| Phase 8 ✅ | Skill Fork Mode 实现 | ✅ 已完成 | _execute_fork 通过子 Agent 执行 |
| Phase 8 ✅ | Agent 版本管理 API | ✅ 已完成 | create/get/rollback 端点均可用 |
| Phase 8 ✅ | HITL Approval 接入 Hook 系统 | ✅ 已完成 | ApprovalManager 注册到 ReActLoop，PRE_TOOL_USE 触发审批 |

---

## 设计文档保真度

| 文档 | 保真度 | 主要问题 |
|------|--------|---------|
| `skills/architecture.md` | ⚠️ 中 | 发现→注册、Manager↔Registry 桥接、SkillContext.tools 注入均已实现；版本管理/Fork 模式/Skill 进化仍为仅文档 |
| `skills/lifecycle.md` | ❌ 极低 | CAPTURED/FIX/DERIVED 进化引擎不存在 |
| `agents/architecture.md` | ✅ 中 | Manager→Registry 桥接已实现；ReActAgent/PlanExecuteAgent 通过 Loop 驱动；所有警告横幅已更新 |
| `harness/index.md` | ⚠️ 低→中 | LangGraph TypedDict 修复；Coordinator 接入 MultiAgent；HeartbeatMonitor 已启动；横幅已更新 |
| `harness/execution.md` | ✅ 中 | ReActLoop Bug 已修复；LangGraph import 已修复；PlanExecuteLoop._execute() 完整实现；横幅已更新 |
| `harness/coordination.md` | ✅ 中 | 6 种协调模式全部接入 MultiAgent；横幅已更新 |
| `framework/patterns.md` | ✅ 中 | Loop 驱动、协调模式、HITL 审批均已接线 |