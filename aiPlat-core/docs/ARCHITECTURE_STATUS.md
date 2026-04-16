# 架构实现状态

> 本文档是 aiPlat-core 各子系统实现状态的**唯一真相来源**。
> 最后更新: 2026-04-16（已纳入持续交付修复：P0/P1/P2 + P0-EXECSTORE）

## 可追溯断言规则（必须遵守｜适用于全仓 docs）

为避免“文档宣称 ≠ 代码事实”与同主题多处矛盾，本文件中所有关键结论必须满足以下规则（适用于：
- `aiPlat-core/docs/**`
- `aiPlat-infra/docs/**`
）：

1) **每条关键结论必须提供证据**（至少其一）：
   - **代码入口**：文件路径 + 关键类/函数名
   - **验证方式**：测试用例路径或可执行命令
2) **同一主题只允许一个最终结论**：若发现多处描述冲突，必须合并为单一结论，并在原位置修订。
3) **状态标记与端到端可用性一致**：
   - ✅：可运行且有基本验证方式
   - ⚠️：可运行但存在已知问题（需写明限制）
   - 🔧：结构存在但未接通（需写明缺失桥接点）

### As-Is / To-Be 写作规范（新增）

为支持“先修订设计文档、再改程序”的工程流程，所有设计文档必须显式区分：
- **As-Is（当前实现）**：以代码事实为准；必须给出证据（代码入口/测试/命令）
- **To-Be（目标架构）**：规划项；必须标注为“规划/未来工作”，并说明预计接线点或受影响模块

禁止将 To-Be 的设想写成 As-Is 的既成事实。

### 证据索引模板（新增）

建议在每份设计文档末尾追加“证据索引（Evidence Index）”，最小包含：
- 代码入口（文件路径 + 关键类/函数）
- 测试/命令（pytest 路径或可执行命令）
- 相关配置（如 env var、config file）——可选

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

**决策**：方案A — Harness Loop 驱动。**主要 Agent（ReAct/PlanExecute/MultiAgent/RAG 等）**通过 `BaseAgent.execute() → self._loop.run(state, config)` 执行；**ConversationalAgent** 作为对话简化路径可保留 `execute()` override（直接调用 model.generate），但必须在文档中明确标注其“非 Loop 驱动”的合理性与边界。

**影响**：
- ReActAgent 的自建推理循环迁移到 ReActLoop._reason/_act/_observe
- PlanExecuteAgent 的自建规划逻辑迁移到 PlanExecuteLoop
- ConversationalAgent 作为对话简化路径保留 override：直接调 model.generate()（不走 Loop）
- BaseAgent._loop 不再是死代码

**证据**：
- 代码入口：
  - `core/apps/agents/base.py: BaseAgent.execute()`
  - `core/harness/execution/loop.py: create_loop() / ReActLoop / PlanExecuteLoop`
  - `core/apps/agents/react.py: ReActAgent.execute()`（委托 `super().execute()`）
  - `core/apps/agents/plan_execute.py: PlanExecuteAgent.execute()`（委托 `super().execute()`）
  - `core/apps/agents/conversational.py: ConversationalAgent.execute()`（保留 override）

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

**证据**：
- 代码入口：`core/apps/agents/base.py: BaseAgent.execute()`（注入 model/tools/skills 后运行 loop）

### 断裂 3：SkillContext.tools 注入 — 🩹 已修复

`SkillExecutor._execute_inline()` 从 skill 的 `config.metadata['tools']` 提取工具名注入 `SkillContext.tools`；`execute_skill` endpoint 创建含 tools 的 `SkillContext`。

### 断裂 4：server execution/history 持久化 — 🩹 已修复（P0-EXECSTORE-001）

此前 `core/server.py` 使用进程内 dict（`_agent_executions/_agent_history/_skill_executions`）保存执行记录，服务重启后查询丢失，且 skill 查询接口存在“未写入 dict”的断裂。

**修复**：引入 SQLite `ExecutionStore`，在 FastAPI lifespan 初始化，并将以下 API 查询端优先读 SQLite（保留内存回退）：
- `GET /api/core/agents/executions/{execution_id}`
- `GET /api/core/agents/{agent_id}/history`
- `GET /api/core/skills/executions/{execution_id}`
- `GET /api/core/skills/{skill_id}/executions`

**证据**：
- 代码入口：
  - `core/services/execution_store.py: ExecutionStore`
  - `core/server.py: lifespan()`（初始化 ExecutionStore）
  - `core/server.py: execute_agent()/execute_skill()`（best-effort 落库）
- 验证方式：
  - `pytest -q core/tests/unit/test_persistence/test_execution_store.py`
  - `pytest -q core/tests/integration/test_execution_store_api.py`

### 断裂 7：ExecutionStore 缺少 schema 迁移/清理策略/Checkpoint 持久化 — 🩹 已修复（P2-EXECSTORE-EXT-001）

此前 ExecutionStore 仅提供最小落库能力，但缺失：
- **schema_version 与迁移机制**：未来加表/加列难以安全升级。
- **清理策略（retention）**：执行历史与 checkpoint 可能无限增长。
- **LangGraph checkpoint 持久化接线**：GraphConfig.enable_checkpoints 仅写入内存 trace，不可重启恢复/回溯。

**修复**：
1) ExecutionStore 增加 schema 迁移机制（幂等）：`aiplat_meta(schema_version)` + `schema_migrations`，当前版本为 `v2`（新增 graph_runs/graph_checkpoints）。
2) 增加 retention 清理策略（best-effort）：
   - `AIPLAT_EXECUTION_DB_RETENTION_DAYS`：按时间删除（created_at/start_time）
   - `AIPLAT_EXECUTION_DB_MAX_ROWS_PER_ENTITY`：每实体（agent_id/skill_id/graph_name）保留最近 N 条
   - `AIPLAT_EXECUTION_DB_PRUNE_ON_START` / `AIPLAT_EXECUTION_DB_VACUUM_ON_PRUNE`
3) 增加 graph_runs/graph_checkpoints 表与最小 API（start/finish/add_checkpoint/list）。
4) LangGraph 执行路径启用 callbacks（GraphConfig.enable_callbacks），server lifespan 注册全局 callback handler，将 GRAPH_START/CHECKPOINT/GRAPH_END best-effort 落库到 ExecutionStore。

**证据**：
- 代码入口：
  - `core/services/execution_store.py: ExecutionStore.init()/prune()/start_graph_run()/add_graph_checkpoint()`
  - `core/harness/execution/langgraph/core.py: CompiledGraph.execute()`（trigger callbacks + graph_run_id）
  - `core/server.py: lifespan()`（注册 LangGraph 回调落库 handler）
- 验证方式：
  - `pytest -q core/tests/unit/test_persistence/test_execution_store_ext.py`

### 断裂 8：TraceService 仅内存态/缺少查询 API — 🩹 已修复（P2-TRACESTORE-001）

此前 TraceService 记录 trace/span/event 仅存在内存对象中，缺少：
- 统一持久化（与 ExecutionStore/GraphRuns 协同）
- 查询接口（无法按 trace_id 回溯，无法分页浏览）

**修复**：
1) ExecutionStore schema 升级为 `v3`：新增 `traces` / `spans` 表（attributes/events JSON）。
2) TraceService 支持可选持久化后端（ExecutionStore），在 start/end trace/span 及 event/attribute 更新时 best-effort 写入 DB。
3) 新增最小查询 API：
   - `GET /api/core/traces`（分页、可按 status 过滤）
   - `GET /api/core/traces/{trace_id}`（含 spans）
   - `GET /api/core/graphs/runs/{run_id}`
   - `GET /api/core/graphs/runs/{run_id}/checkpoints`

**证据**：
- 代码入口：
  - `core/services/execution_store.py`（v3 migrations + upsert_trace/upsert_span/get_trace/list_traces）
  - `core/services/trace_service.py`（持久化写入 + TraceServiceTracer）
  - `core/server.py`（新增 trace/graph 查询 API + tracer wiring）
- 验证方式：
  - `pytest -q core/tests/unit/test_persistence/test_execution_store_trace.py`
  - `pytest -q core/tests/integration/test_trace_api.py`

### 断裂 9：Checkpoint 缺少 restore/resume 语义 + execution_id 与 trace_id 未关联 — 🩹 已修复（P2-RESUME-001）

此前存在两类断裂：
- **Checkpoint 不可恢复执行**：checkpoint state 未显式包含 `current_node`，且 CompiledGraph 固定从 entry_point 开始，无法从 checkpoint 继续。
- **execution_id 与 trace_id 断链**：即便 Trace/Span 已落库，也难以定位某次 agent/skill 执行对应哪条 trace。

**修复**：
1) ExecutionStore schema 升级为 `v4`：
   - `graph_runs` 增加 `parent_run_id / resumed_from_checkpoint_id`（恢复链路）
   - `agent_executions / skill_executions` 增加 `trace_id`（执行与 trace 关联）
2) CompiledGraph 执行语义增强：
   - state 中写入/更新 `current_node`，checkpoint state 可携带恢复点
   - 若 initial_state 已包含 `current_node`，则从该节点继续执行（restore/resume）
3) 新增 Graph restore/resume API：
   - `GET /api/core/graphs/runs/{run_id}/checkpoints/{checkpoint_id}`
   - `POST /api/core/graphs/runs/{run_id}/resume`（基于 checkpoint 创建新 run 并返回恢复状态）
4) 在 agent/skill 执行路径中创建 Trace 并回写 trace_id 到 execution_record（best-effort），实现 execution↔trace 关联。

**证据**：
- 代码入口：
  - `core/services/execution_store.py`（v4 migrations + resume_graph_run/get_graph_checkpoint + trace_id 列）
  - `core/harness/execution/langgraph/core.py: CompiledGraph.execute()`（current_node 恢复）
  - `core/server.py`（graphs resume API + execute_agent/execute_skill 写入 trace_id）
- 验证方式：
  - `pytest -q core/tests/unit/test_harness/test_execution/test_langgraph_resume.py`
  - `pytest -q core/tests/integration/test_graph_resume_api.py`

### 断裂 10：resume 仅返回 state / callbacks 未落库（register_global 缺失）— 🩹 已修复（P2-RESUME-EXEC-001）

此前仍存在“看似有 checkpoint/回调，但无法形成可用闭环”的问题：
- `CallbackManager` 缺少 `register_global()` 方法，导致 server lifespan 中的落库 handler 注册失败（被 try/except 吞掉），checkpoint 实际未写入 SQLite。
- `/graphs/runs/{run_id}/resume` 仅创建新 run 并返回恢复 state，上层无法直接“恢复并继续执行”（缺少一键闭环）。

**修复**：
1) 为 `CallbackManager` 增加 `register_global()`，确保 GRAPH_START/CHECKPOINT/GRAPH_END 事件可被进程级 handler 捕获并落库。
2) 修复 ReasonNode prompt 的 f-string 花括号转义问题（`{json_or_text}` → `{{json_or_text}}`），避免执行时报 NameError。
3) 引入 CompiledGraph-based ReAct 参考实现（不依赖外部 langgraph），并提供闭环 API：
   - `POST /api/core/graphs/compiled/react/execute`
   - `POST /api/core/graphs/runs/{run_id}/resume/execute`
   该路径可触发 callbacks→写入 ExecutionStore（graph_runs/graph_checkpoints），并支持从 checkpoint state（current_node）继续执行。

**证据**：
- 代码入口：
  - `core/harness/execution/langgraph/callbacks.py: CallbackManager.register_global()`
  - `core/harness/execution/langgraph/compiled_graphs/react.py: create_compiled_react_graph()`
  - `core/server.py`（compiled graph execute + resume/execute API）
- 验证方式：
  - `pytest -q core/tests/integration/test_compiled_react_resume_execute_api.py`

### 断裂 11：ReActGraph/LangGraphExecutor 无法形成闭环 + execution↔trace 缺少联查 + resume 缺少幂等/权限 — 🩹 已修复（P2-CLOSELOOP-001）

在 Round12 之前，闭环能力仍局限于“compiled_react 参考路径”，并存在三类剩余问题：
1) **推广缺失**：`graphs/react.py` 的 ReActGraph 仍尝试实例化 TypedDict（运行期错误），`UnifiedExecutor/LangGraphExecutor` 走该路径会失败；同时缺少统一的 callbacks/checkpoints 口径。
2) **联查缺失**：已有 trace_id 字段写入 execution 记录，但缺少 API 支持按 execution_id 获取 trace，或按 trace_id 反查 executions。
3) **resume 语义不完整**：重复 resume 同一 checkpoint 会创建多条 run 记录；且缺少按 graph_name 的权限约束（用户可随意 resume/execute）。

**修复**：
1) 将 `ReActGraph.run()` 默认实现切换为内部 CompiledGraph 引擎（支持 callbacks/checkpoints），并扩展 ReActGraphConfig 支持 enable_checkpoints/checkpoint_interval/enable_callbacks。
2) ExecutionStore 增加联查方法与 API：
   - `GET /api/core/executions/{execution_id}/trace`
   - `GET /api/core/traces/{trace_id}/executions`
3) 强化 resume：
   - ExecutionStore.resume_graph_run 增加幂等：若已存在 parent_run_id+resumed_from_checkpoint_id 的 run，则返回该 run。
   - 新增唯一索引 `idx_graph_runs_resume_unique`（best-effort 创建），并在 resume/resume_execute API 中加入基于 `graph:{graph_name}` 的权限校验（非 system 用户）。

**证据**：
- 代码入口：
  - `core/harness/execution/langgraph/graphs/react.py`（ReActGraph.run 使用 CompiledGraph）
  - `core/services/execution_store.py`（resume 幂等 + execution↔trace 联查）
  - `core/server.py`（联查 API + resume 权限校验）
- 验证方式：
  - `pytest -q core/tests/integration/test_execution_trace_link_api.py`
  - `pytest -q core/tests/integration/test_compiled_react_resume_execute_api.py`

### 断裂 5：Tool Calling 解析口径不统一（ACTION 文本不稳定）— 🩹 已修复（P1-TOOLCALL-001）

此前工具调用依赖 LLM 输出自由文本 `ACTION:`，存在：
- 解析脆弱（多余文本/JSON fenced/尾随解释导致解析失败）
- LangGraph / Loop 两套解析逻辑不一致（LangGraph 仅取 tool_name 且丢 args）

**修复**：引入统一解析器 `parse_tool_call()`，约定“结构化优先，ACTION 兜底”：
- 结构化（推荐）：
  - `{"tool":"tool_name","args":{...}}`
  - `{"name":"tool_name","arguments":"{...json...}"}`（兼容 OpenAI style）
- 旧格式（兼容）：
  - `ACTION: tool_name: {json_or_text}`

并接线到：
- `core/harness/execution/loop.py: ReActLoop._act()`（Loop-first 主路径）
- `core/harness/execution/langgraph/nodes/act_node.py` 与 `reason_node.py`（Graph 子系统）

**证据**：
- 代码入口：
  - `core/harness/execution/tool_calling.py: parse_tool_call()`
  - `core/harness/execution/loop.py: ReActLoop._act()`（使用 parse_tool_call）
  - `core/harness/execution/langgraph/nodes/act_node.py`（使用 parse_tool_call）
- 验证方式：
  - `pytest -q core/tests/unit/test_harness/test_execution/test_tool_calling.py`

### 断裂 6：Skill/Tool 路由存在 substring 误触发 — 🩹 已修复（P1-ROUTING-001）

此前存在“只要文本包含名字就执行”的路由逻辑，典型问题：
- `ReActLoop._act()` 在工具未命中时，会对 skills 做 `skill_name in reasoning.lower()` 的 substring 匹配，容易误触发（例如解释文本中提到 skill 名称）。
- `PlanExecuteLoop._execute()` 使用 `tool_name.lower() in action.lower()` / `skill_name.lower() in action.lower()` 来决定执行哪个 tool/skill，属于高风险隐式路由。

**修复**：将 tool/skill 的执行决策统一收敛为“显式路由优先”：
- 新增 `parse_action_call()`：支持显式 `{"skill": "...", "args": {...}}` / `SKILL: ...`，并避免用 substring 推断 skill/tool。
- `ReActLoop._act()`：仅在解析到显式 skill_call 时执行 skill；否则只执行明确的 tool_call（或返回 not found）。
- `PlanExecuteLoop._execute()`：仅当 plan step 里出现显式 JSON（tool/skill）时才执行对应能力；并在 planning prompt 中要求 model 用结构化 JSON 表达需要调用 tool/skill 的步骤。

**证据**：
- 代码入口：
  - `core/harness/execution/tool_calling.py: parse_action_call()`
  - `core/harness/execution/loop.py: ReActLoop._act()`（移除 substring skill fallback）
  - `core/harness/execution/loop.py: PlanExecuteLoop._plan/_execute()`（移除 substring tool/skill dispatch）
- 验证方式：
  - `pytest -q core/tests/unit/test_harness/test_execution/test_tool_calling.py`

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

**证据（抽样）**：
- Skill Fork Mode：
  - 代码入口：`core/apps/skills/executor.py: SkillExecutor._execute_fork()`
  - 测试：`core/tests/unit/test_skills/test_executor_fork.py`
- Skill 版本查询（审计/回滚验证）：
  - 代码入口：`core/server.py: get_skill_version()`
  - 测试：`core/tests/unit/test_skills/test_version_api.py`

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
| MultiAgent | ✅ | 使用 Harness Coordination Patterns（Pipeline/FanOut/Expert/Producer/Supervisor/HierarchicalDelegation） |
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

**证据（抽样）**：
- PermissionManager：
  - 代码入口：`core/apps/tools/permission.py: PermissionManager.grant_permission/check_permission/get_stats`
  - 测试：`core/tests/unit/test_tools/test_permission_manager.py`
- Tool 统一执行封装（追踪/超时/异常/统计）：
  - 代码入口：`core/apps/tools/base.py: BaseTool._call_with_tracking() / ToolRegistry.set_permission_manager()/register()`
  - 测试：`core/tests/unit/test_tools/test_tool_tracking.py`

### Harness 系统

| 组件 | 状态 | 说明 |
|------|------|------|
| Policy Engine | ✅ | 策略规则完整可用 |
| Memory 系统 | ✅ | 短期/工作/情景/语义四层 |
| Knowledge 检索 | ⚠️ | 可用但使用 hash 伪向量 |
| Hook 系统 | ✅ | 修复 PRE_SKILL_USE→POST_SKILL_USE Bug |
| Coordination 模式 | ✅ | 6 种模式（Pipeline/FanOut/Expert/Producer/Supervisor/HierarchicalDelegation）已接入 MultiAgent.execute() 并可被调用 |
| Convergence 检测 | ✅ | 4 种检测器可用，且已接入 LangGraph MultiAgentGraph 收敛评估路径 |
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

**证据（抽样）**：
- Coordination 模式接入：
  - 代码入口：`core/harness/coordination/patterns/base.py: create_pattern() / HierarchicalDelegationPattern`
  - 代码入口：`core/apps/agents/multi_agent.py: MultiAgent._create_pattern() / _PatternAgentAdapter`
  - 测试：`core/tests/unit/test_harness/test_coordination/test_hierarchical_delegation.py`
  - 契约保护测试：`core/tests/unit/test_harness/test_coordination/test_pattern_contract.py`
- ConvergenceDetector 接入：
  - 代码入口：`core/harness/execution/langgraph/graphs/multi_agent.py: _evaluate_convergence()`
  - 代码入口：`core/harness/coordination/detector/convergence.py: create_detector()`
  - 测试：`core/tests/unit/test_harness/test_convergence/test_langgraph_multi_agent_convergence.py`

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
| P3 ✅ | Coordination 模式接入 MultiAgent | ✅ 已完成 | 6 种模式全部接入 MultiAgent.execute() |
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
