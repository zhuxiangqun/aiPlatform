# 03｜执行引擎与路由（Engines & Routing）

状态：草案（Phase 5 设计；当前实现仍为 Loop-first 直连执行）  
更新时间：2026-04-16

---

## 0. 现状对齐（As-Is vs To-Be）

> 本文是 Phase 5（P1）的设计目标；当前代码实现尚未引入 EngineRouter/Orchestrator/ExecutionPlan 体系，因此需要先明确 As‑Is 运行态与缺口。

As-Is（当前实际运行态）：
- API 执行入口：`core/server.py` → `core/harness/integration.py::HarnessIntegration.execute`
- 执行引擎：
  - agent：主要通过 `core/apps/agents/base.py` 注入 loop 并执行（Loop-first）
  - graph：`HarnessIntegration._execute_graph` 直接执行 langgraph（没有统一 Router 层）
- 治理入口：
  - Tool/Skill/LLM 副作用在主链路上已尽量经 syscalls（但仍存在绕过点，见 02 文档静态扫描）

To-Be（Phase 5 目标）：
- 引入 `ExecutionPlan + PromptContext -> ExecutionResult` 的统一执行接口
- 引入 `EngineRouter`，把 loop/langgraph/未来 agentloop 统一为 engine，并支持可观测 fallback 链（graph→loop→quick）
- Orchestrator 只产出 plan（严禁副作用），并把 explain/fallback_trace 落库

当前未落地的原因（简述）：
- 需要先完成 Phase 4 的 PromptContext/PromptAssembler 收敛，否则 Engine 接口无法做到“禁止 engine 自行拼 prompt”
- 需要冻结 contracts（01-contracts.md Phase 4+），否则 ExecutionPlan/PromptContext 字段会频繁漂移，难以落库/回放/验收

## 1. 目标

- 在不破坏“治理必经/不可绕过”的前提下，吸收 rangen_core 的多引擎上限：
  - Loop-first 主引擎（稳定可控）
  - LangGraph 插件引擎（高上限编排）
  -（后续）AgentLoop 流式引擎
- 统一引擎接口与输入输出：`ExecutionPlan + PromptContext -> ExecutionResult`
- 支持可观测的 fallback 链：graph → loop → quick

---

## 2. To-Be 代码落点

- 引擎接口：`core/harness/execution/engines/base.py`（新增）
- 引擎实现：
  - `core/harness/execution/engines/loop_engine.py`（新增）
  - `core/harness/execution/engines/langgraph_engine.py`（新增）
  - `core/harness/execution/engines/agentloop_engine.py`（可选新增）
- 路由器：`core/harness/execution/router.py`（新增）

As-Is（当前替代实现/临时结构）：
- Loop 执行：`core/harness/execution/loop.py`
- LangGraph 执行：`core/harness/integration.py::_execute_graph` + `core/harness/execution/langgraph/*`

---

## 3. 引擎接口（冻结）

```python
class IExecutionEngine(Protocol):
    name: str
    async def execute(self, plan: ExecutionPlan, ctx: PromptContext) -> ExecutionResult: ...
```

约束：
- 引擎内部不得直接调用 tool/llm/skill：必须通过 syscalls
- 引擎不得自行组装 prompt：必须消费 PromptContext（必要时调用 PromptAssembler，但也应在 Kernel 侧完成）

冻结前置条件（必须达成）：
- Phase 2 静态扫描清零（禁止 engine/agent 层 `tool.execute/.generate/skill.execute`，见 02 文档）
- Phase 4 PromptContext/PromptAssembler 落地（`core/harness/assembly/*`）
- Phase 4+ contracts 冻结（`01-contracts.md`）

---

## 4. LoopEngine（主引擎）

### 4.1 As-Is 依赖
- `core/harness/execution/loop.py`：ReActLoop/PlanExecuteLoop
- `core/apps/agents/*`：agent config/loop_type

### 4.2 To-Be 适配策略
- LoopEngine 根据 `plan.plan_type` 选择：
  - reasoning → ReActLoop
  - planning → PlanExecuteLoop
  - quick → QuickLoop（可选：直接一次 LLM call）
- Loop 的 LLM/Tool/Skill 调用全部改为 syscalls

As-Is 对齐点（当前已实现/部分实现）：
- ReActLoop 已对 sys_tool 返回的 `approval_required/policy_denied` 做 PAUSED 处理，并可通过 loop_state_snapshot 续跑
- Tool/Skill/LLM 的 syscall 级审计已写入 ExecutionStore（syscall_events）

---

## 5. LangGraphEngine（插件引擎）

### 5.1 As-Is 依赖
- `core/harness/execution/langgraph/graphs/*`
- `core/harness/execution/langgraph/callbacks.py`（已具备持久化 hook）

### 5.2 To-Be 适配策略
- LangGraphEngine 仅在 plan 指示或 router 决策时启用
- Graph nodes 内部不得直接执行 tool/llm：必须通过 syscalls
- CallbackManager 必须写入 trace_id/run_id 关联信息，保证回放一致

---

## 6. EngineRouter（路由与回退）

### 6.1 基本规则（默认）
- 默认：Loop-first
- 仅当 plan_type 指示（例如 multi_agent/tri_agent/reflection）或策略命中时，进入 LangGraph

### 6.2 fallback 链（建议）
- 首选引擎失败：
  - 如果失败可恢复（timeout/tool_error）：尝试下一个引擎
  - fallback 轨迹必须记录在 ExecutionResult.metadata

伪代码：
```python
for engine in plan.fallback_chain:
    try:
        return await engines[engine].execute(plan, ctx)
    except Exception as e:
        record_fallback(engine, e)
return failed_result
```

### 6.3 一致性保证（关键）
- Policy/Trace/Context/Resilience 均在 Kernel 层实现，Engine 只“消费能力”
- 任何 engine 都不拥有独立的 Permission/Trace/Retry 逻辑（避免分叉）

---

## 7. 分期落地方案（建议）

> 目标：让 Phase 5 可独立上线、可回滚、可验收。

### 7.1 Phase 5.0：只引入接口壳（不改变执行路径）
- 新增 engines/base.py + router.py，但 Router 固定返回 LoopEngine（不启用 langgraph）
- 引入 ExecutionPlan（最小字段）与 explain 落库（ExecutionStore）
- 验收：
  - Router/Engine 接口存在且被 HarnessIntegration 调用
  - explain/engine 选择写入执行记录（可查询）

### 7.2 Phase 5.1：引入可观测 fallback（但默认仍 Loop-first）
- 允许 plan 指示进入 langgraph
- 失败时按 fallback_chain 回退到 loop
- 验收：
  - fallback_trace 写入 ExecutionResult.metadata 并落库
  - 失败原因链可复现（审计接口可查询）

### 7.3 Phase 5.2：引入 Orchestrator（只产 plan）
- 新增 `core/orchestration/*`：只生成 ExecutionPlan，不允许副作用调用
- 验收：
  - Orchestrator 层静态扫描：无 tool/skill/llm 副作用调用（CI 阻断）
  - plan explain 覆盖率 ≥ 99%（每次执行都能给出 explain）

---

## 8. 评审检查清单

- [ ] 引擎接口是否满足未来 AgentLoop 的接入？
- [ ] LangGraph nodes 如何改造以确保 syscalls 必经？
- [ ] fallback 链是否可观测、可解释、可审计？
- [ ] Loop-first 主引擎策略是否与现有系统成熟度匹配？

## 9. 冻结前置条件（强约束）

1) Phase 2：静态扫描清零（不可绕过）
2) Phase 4：PromptContext/PromptAssembler 落地并写入 prompt_version
3) ExecutionPlan/PromptContext/ExecutionResult 契约冻结并具备回放兼容策略
