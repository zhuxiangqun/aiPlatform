# aiPlat-core 内核化改造：设计文档方案（先文档、后改代码）
更新时间：2026-04-16

> 目的：在进入程序改造前，先产出一套可评审、可落地、可验收的设计文档（Design Doc）集合。  
> 原则：**先冻结契约与边界，再改实现；先主链路闭环，再扩展多路径与自学闭环。**

---

## 1. 设计文档交付物清单（建议 6 份）

> 这些文档确认通过后，再进入代码改造阶段（按 Phase 推进）。

1) **总体设计（Architecture Design Doc）**（必需）
   - 文件：`docs/design/kernel_orchestrator/00-architecture.md`
   - 内容：Kernel/User-space 分层、模块边界、依赖方向、运行时主链路、关键取舍。

2) **核心契约与数据模型（Contracts & Types）**（必需）
   - 文件：`docs/design/kernel_orchestrator/01-contracts.md`
   - 内容：`ExecutionRequest / PromptContext / ExecutionPlan / ExecutionResult`、syscalls 入参出参、错误模型、状态机、版本策略。

3) **Syscalls 与 Gates 设计（Kernel Runtime）**（必需）
   - 文件：`docs/design/kernel_orchestrator/02-syscalls-and-gates.md`
   - 内容：`sys_llm/sys_tool/sys_skill` 的职责、四大 Gate 的执行时序与不可绕过保证、接入点（Integration / Engine / ToolCalling）。

4) **执行引擎与路由（Execution Engines & Routing）**（必需）
   - 文件：`docs/design/kernel_orchestrator/03-engines-and-routing.md`
   - 内容：Loop-first 主引擎、LangGraph 插件引擎、EngineRouter/fallback 链、如何保证治理一致性与可观测性一致性。

5) **安全与合规（Security/Approval/Audit）**（必需）
   - 文件：`docs/design/kernel_orchestrator/04-security-and-audit.md`
   - 内容：权限模型、审批模型（默认：同步阻塞 + 可恢复）、审计记录字段、敏感操作定义与策略、CI 防绕过规则。

6) **实施计划与验收（Migration Plan & Acceptance）**（必需）
   - 文件：`docs/design/kernel_orchestrator/05-migration-and-acceptance.md`
   - 内容：分期（Phase 1~6）改动面、回滚方案、回归测试、验收标准（可量化指标）、风险与缓解。

> 可选补充（后续再补，不阻塞第一轮改造）：
> - 自学闭环（Evaluation/Feedback/Evolution）详细设计
> - 性能与容量评估（perf/cost）

---

## 2. 设计文档统一约束（写作口径）

1) **必须以代码为准**：文档每个组件都要映射到现有目录/类（As-Is）与 To-Be 的落点（含新增文件路径）。
2) **契约先行**：先定义 types 与 syscall 接口，再定义具体引擎怎么调用。
3) **可观测/可回放是第一等公民**：每条主链路必须说明 run_id/trace_id 如何产生与传递、落库字段。
4) **禁止绕过机制**：每个设计必须回答“如何保证不可绕过？”（代码层 + CI 层）。
5) **兼容策略**：Phase 1~3 必须做到“不改变业务行为或最小漂移”，并写清楚兼容开关。

---

## 3. 各文档详细大纲（可直接复制为模板）

### 3.1 00-architecture.md（总体设计）
- 背景与目标（北极星约束）
- As-Is 现状概览（server/management/apps/harness/services）
- To-Be 分层（Kernel vs User-space）
- 关键组件图（Mermaid：架构图 + 时序图）
- 依赖方向与禁止依赖
- 核心取舍（为何 Orchestrator 不进 Kernel；为何 Loop-first）
- 风险清单（分叉风险、行为漂移、性能回归）与策略

### 3.2 01-contracts.md（契约与类型）
- 总览：4 大核心对象 + 3 大 syscall 对象
- `ExecutionRequest` 字段定义（含来源：HTTP/上游）
- `PromptContext` 字段定义（含 budgets/artifacts/tool_schemas）
- `ExecutionPlan` 字段定义（plan_type/engine_hint/fallback/explain）
- `ExecutionResult` 字段定义（status/trace/tool_calls/token_usage/metadata）
- 错误模型：错误码、可重试/不可重试、审批态
- 版本策略：字段新增/变更、向后兼容

### 3.3 02-syscalls-and-gates.md（syscalls 与 gates）
- Syscalls 设计：
  - `sys_llm.generate(LLMRequest)->LLMResult`
  - `sys_tool.call(ToolCall)->ToolResult`
  - `sys_skill.call(SkillCall)->SkillResult`
- Gate 设计：
  - PolicyGate（Permission+Approval）
  - TraceGate（TraceService/ExecutionStore）
  - ContextGate（budget/compaction）
  - ResilienceGate（retry/fallback/timeout/circuit）
- 执行时序：Integration → Gates → Engine → Syscalls → Result
- 不可绕过保证：代码结构 + CI 扫描规则（示例规则）
- 数据落库：每次 syscall 必须记录哪些字段

### 3.4 03-engines-and-routing.md（引擎与路由）
- 引擎接口：`IExecutionEngine.execute(plan, prompt_context)->ExecutionResult`
- LoopEngine（ReActLoop/PlanExecuteLoop）适配方案
- LangGraphEngine 适配方案（callback + checkpoint + tracing）
- EngineRouter 规则（默认 loop-first，graph 为特定 plan）
- fallback 链：graph→loop→quick（由 ResilienceGate 执行）
- 一致性约束：上下文/权限/审计/追踪的“一致实现点”

### 3.5 04-security-and-audit.md（安全与审计）
- 资产分类：tool/skill/agent/mcp（危险等级与默认策略）
- 权限模型：RBAC（已存在 PermissionManager）如何被 Kernel 强制使用
- 审批模型：同步阻塞（approval_required）+ 恢复执行（resumed）
- 审计字段：tool_calls、审批决策、用户身份、上下文摘要、模板版本
- 误用防护：禁止直连 tool/llm；禁止 server 绕过 integration
- CI/Hook：静态扫描 + pre-commit 示例

### 3.6 05-migration-and-acceptance.md（实施与验收）
- 分期计划（Phase 1~6）
- 每期改动点（到文件路径/模块）
- 兼容开关（feature flags）
- 回滚策略（按期）
- 回归测试策略：
  - 主链路回归（agent execute）
  - 工具调用治理（权限/审批）
  - trace/run 回放一致性
- 验收指标：
  - 覆盖率：syscalls 覆盖比例
  - 治理：敏感工具审批命中率/绕过为 0
  - 可观测：trace/span 完整率

---

## 4. 评审流程与通过标准（建议）

### 4.1 评审顺序（从“最硬约束”到“实现细节”）
1) 00 总体设计 → 01 契约（冻结）  
2) 02 syscalls/gates（冻结“不可绕过”机制）  
3) 03 引擎与路由（确认 Loop-first 与 fallback）  
4) 04 安全与审计（确认合规口径）  
5) 05 实施与验收（确认分期与回滚）

### 4.2 通过标准（满足即进入代码改造）
- 核心契约（types + syscalls）字段与版本策略冻结
- 明确唯一入口与禁止绕过清单（含 CI 规则草案）
- Phase 1~3 具备“可上线且不改变行为”的路径
- 每期都有可量化验收指标与回滚策略

---

## 5. 下一步（我建议的工作方式）

我可以直接按上述方案在仓库里生成 `docs/design/kernel_orchestrator/` 目录下的 **6 份设计文档模板**（带标题、章节占位、Mermaid 图占位、以及对应现有代码路径的“待填项”列表），然后你评审确认后，我们再进入 Phase 1 的代码改造。

