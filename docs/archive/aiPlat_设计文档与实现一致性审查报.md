aiPlat 设计文档与代码一致性审查报告

范围：aiPlat-core / aiPlat-infra / aiPlat-management / root-docs

重点：整体架构与模块边界 / Harness / Agent / Skill / Tool /
core↔infra↔management 边界契约

结论摘要

总审查项：11；风险分布：中 8，低 1，高 2

说明：本报告以["]{dir="rtl"}设计文档原文 +
代码证据"为最终判定依据；若文档自相矛盾，则在问题项中显式标注并给出修订建议。

问题清单（总览）

  ----------------------- ------ ------------------ ----------------------------------- ------------------------------------------
  **ID**                  风险   判定               问题类型                            来源文档

  DOC-STATUS-001          中     ⚠️部分一致         文档自相矛盾/来源权威性风险         aiPlat-core/docs/ARCHITECTURE_STATUS.md

  HARN-COORD-001          中     ❌不一致           设计文档与实现不一致/文档内部矛盾   aiPlat-core/docs/harness/coordination.md

  HARN-COORD-002          中     ⚠️部分一致         接口契约不清晰/易误用               aiPlat-core/docs/harness/coordination.md

  HARN-CONV-001           低     🔧结构存在未接通   结构存在但关键桥接缺失              aiPlat-core/docs/harness/coordination.md

  AGENT-EXEC-001          中     ⚠️部分一致         死代码/重复实现风险                 aiPlat-core/docs/ARCHITECTURE_STATUS.md

  SKILL-FORK-001          高     ❌不一致           实现不合理/运行期必错风险           aiPlat-core/docs/ARCHITECTURE_STATUS.md

  SKILL-VERSION-API-001   中     ❌不一致           API 契约缺口/不可用实现             aiPlat-core/docs/skills/architecture.md

  TOOL-DOC-IMPL-001       中     ❌不一致           文档漂移/设计未落地                 aiPlat-core/docs/tools/index.md

  TOOL-PERM-001           高     ❌不一致           实现不合理/潜在缺陷                 aiPlat-core/docs/tools/index.md

  INFRA-OBS-001           中     ❌不一致           文档漂移/实现降级未披露             aiPlat-infra/docs/observability/index.md

  INFRA-DI-001            中     ❌不一致           文档漂移/功能未落地                 aiPlat-infra/docs/di/index.md
  ----------------------- ------ ------------------ ----------------------------------- ------------------------------------------

逐条审查明细

DOC-STATUS-001（中）

来源文档：aiPlat-core/docs/ARCHITECTURE_STATUS.md

设计声明：["]{dir="rtl"}架构实现状态"作为唯一真相来源，应当在同一主题上保持自洽、可复核且不自相矛盾。

判定：⚠️部分一致

问题类型：文档自相矛盾/来源权威性风险

代码/文档证据：

doc \| aiPlat-core/docs/ARCHITECTURE_STATUS.md \|
该文档自称["]{dir="rtl"}唯一真相来源"，但在 Coordination
模式是否接入/是否被调用等表述上存在冲突风险，需要以代码实证裁决。

修正建议：对 ARCHITECTURE_STATUS.md
建立["]{dir="rtl"}可追溯断言"机制：每条状态声明附带对应代码入口/关键函数名（或测试用例链接）；若同主题有不同段落表述，必须合并为单一结论并注明版本。

验证方法：抽查 3-5 个主题（例如 Coordination / Skill Fork /
Permission），确保每条状态声明都能在代码中定位到入口或明确标注为["]{dir="rtl"}仅文档"。

HARN-COORD-001（中）

来源文档：aiPlat-core/docs/harness/coordination.md

设计声明：协调模式数量与清单应在同一文档内部保持一致，且与工厂
create_pattern() 支持的模式一致。

判定：❌不一致

问题类型：设计文档与实现不一致/文档内部矛盾

代码/文档证据：

doc \| aiPlat-core/docs/harness/coordination.md \| 文档第 3
行提示["]{dir="rtl"}5 种模式接入"，但后续第 28
行又声明["]{dir="rtl"}所有 6 种模式...合并实现"，并给出了第 6 种
Hierarchical Delegation 描述。

code \| aiPlat-core/core/harness/coordination/patterns/base.py \|
create_pattern() 仅支持 pipeline / fan_out_fan_in / expert_pool /
producer_reviewer / supervisor（共 5 种），不存在
hierarchical_delegation。

修正建议：统一 coordination.md：明确当前实现仅 5 种模式；若需要第 6 种
Hierarchical Delegation，则补充实现与工厂映射，并在 MultiAgentConfig
中纳入一致命名。

验证方法：运行时：MultiAgent 选择每种模式均可触发对应
Pattern；静态：coordination.md 中模式清单与 create_pattern() 映射一致。

HARN-COORD-002（中）

来源文档：aiPlat-core/docs/harness/coordination.md

设计声明：Coordination Pattern 的接口契约应与 Agent 的真实 execute()
形态一致，避免["]{dir="rtl"}模式实现假设 execute
接受字符串"导致潜在误用。

判定：⚠️部分一致

问题类型：接口契约不清晰/易误用

代码/文档证据：

code \| aiPlat-core/core/harness/coordination/patterns/base.py \|
Pattern 内部直接调用 agent.execute(context.task)；该调用默认传入字符串
task。

code \| aiPlat-core/core/apps/agents/multi_agent.py \| MultiAgent 通过
\_PatternAgentAdapter 将字符串 task_input 包装成 AgentContext
后再调用真实 Agent.execute(AgentContext)，表明 Pattern
的["]{dir="rtl"}agent.execute(str)"并非真实 Agent 契约，而是依赖适配器。

修正建议：将 ICoordinationPattern 的约束显式化：要求 agents
列表传入统一适配器接口（如 PatternAgentAdapter），或把
CoordinationContext.task 改为 AgentContext 并统一由 Pattern
内部创建子上下文。

验证方法：新增单测：直接用真实 Agent（非适配器）传入 Pattern
时应显式失败并给出清晰错误；或确保 Pattern API 层面无法传入不兼容对象。

HARN-CONV-001（低）

来源文档：aiPlat-core/docs/harness/coordination.md

设计声明：文档提到
ConvergenceDetector，应明确其是否接入实际执行链路；若未接入，应在文档与状态索引中一致标注。

判定：🔧结构存在未接通

问题类型：结构存在但关键桥接缺失

代码/文档证据：

code \| aiPlat-core/core/harness/coordination/detector/convergence.py \|
存在 ConvergenceDetector 相关实现与接口。

code \|
aiPlat-core/core/harness/execution/langgraph/graphs/multi_agent.py \|
收敛判断使用 set(result) 的简单比较逻辑，未见对 ConvergenceDetector
的调用。

code \| aiPlat-core/core/harness/integration.py \| HarnessIntegration
提供 create_convergence_detector() 工厂入口，但不等于被执行路径使用。

修正建议：若设计目标为可插拔收敛检测：在 MultiAgent 的 LangGraph 图或
MultiAgent.execute() 中注入并调用 ConvergenceDetector；否则，删减
ConvergenceDetector 的设计描述并在 docs
明确降级为["]{dir="rtl"}简单一致性判断"。

验证方法：为 MultiAgent 增加配置项：选择
detector_type；验证在执行路径中调用对应 detector，并可通过不同 detector
得到不同收敛结论。

AGENT-EXEC-001（中）

来源文档：aiPlat-core/docs/ARCHITECTURE_STATUS.md

设计声明：Agent 执行路径应统一由 BaseAgent.execute() → Loop
驱动，子类尽量不自建推理循环，避免重复实现与行为漂移。

判定：⚠️部分一致

问题类型：死代码/重复实现风险

代码/文档证据：

doc \| aiPlat-core/docs/ARCHITECTURE_STATUS.md \| ["]{dir="rtl"}决策
2：Agent 执行路径"声明采用 Harness Loop 驱动。

code \| aiPlat-core/core/apps/agents/react.py \| ReActAgent.execute()
已委托 super().execute()，但文件内仍保留
\_execute_reasoning_loop/\_reason/\_act/\_observe
等自建循环逻辑片段（维护与理解成本高）。

修正建议：清理或隔离旧循环实现：若已完全迁移至
ReActLoop，则删除旧逻辑；若仍需保留，至少加显式注释与测试证明其仍可达，并避免与
Loop 驱动产生双路径。

验证方法：静态：grep 确认旧方法无调用者则移除；动态：对 ReActLoop
的关键步骤（reason/act/observe）补充单测覆盖。

SKILL-FORK-001（高）

来源文档：aiPlat-core/docs/ARCHITECTURE_STATUS.md

设计声明：Skill fork 模式应能稳定创建子 Agent
并执行，不应出现构造签名不匹配导致运行期错误。

判定：❌不一致

问题类型：实现不合理/运行期必错风险

代码/文档证据：

code \| aiPlat-core/core/apps/skills/executor.py \|
SkillExecutor.\_execute_fork() 以 ConversationalAgent(name=\...,
system=\...) 方式构造 agent。

code \| aiPlat-core/core/apps/agents/conversational.py \|
ConversationalAgent.\_\_init\_\_(config: AgentConfig, model:
Optional\[ILLMAdapter\], \...)；并提供
create_conversational_agent(config, model, system_prompt) 工厂。

修正建议：将 \_execute_fork() 改为：构造 AgentConfig 后调用
create_conversational_agent()；或通过 Agent 工厂 create_agent()
创建并注入 model/config，避免直接硬编码构造参数。

验证方法：新增用例：以 mode=fork 执行任意 Skill，确保能返回 SkillResult
且不抛 TypeError；并验证子 Agent 的 system_prompt 生效。

SKILL-VERSION-API-001（中）

来源文档：aiPlat-core/docs/skills/architecture.md

设计声明：Skill 版本查询应返回可用的版本配置（至少包含
metadata/config），否则无法支撑审计与回滚验证。

判定：❌不一致

问题类型：API 契约缺口/不可用实现

代码/文档证据：

code \| aiPlat-core/core/server.py \| GET
/skills/{skill_id}/versions/{version} 读取 registry.get_version() 但返回
{\"config\": {}}（丢失实际配置）。

修正建议：返回 registry.get_version()
的真实内容（或其可序列化视图），并与 SkillConfig/SkillInfo
的字段对齐；若涉及敏感字段，则做脱敏而非置空。

验证方法：创建 Skill 版本后，调用 versions/{version}
能拿到与创建时一致的 config/metadata；随后 rollback
可基于该配置进行一致性检查。

TOOL-DOC-IMPL-001（中）

来源文档：aiPlat-core/docs/tools/index.md

设计声明：工具系统文档宣称的能力（追踪注入、权限注入、\_call_with_tracking、统计封装）应在
BaseTool/ToolRegistry 中有对应实现或明确标注为["]{dir="rtl"}仅文档"。

判定：❌不一致

问题类型：文档漂移/设计未落地

代码/文档证据：

doc \| aiPlat-core/docs/tools/index.md \| 文档宣称 BaseTool/ToolRegistry
支持["]{dir="rtl"}带追踪的执行：\_call_with_tracking()、权限校验自动注入"等。

code \| aiPlat-core/core/apps/tools/base.py \| BaseTool 仅实现
validate_params/\_update_stats；ToolRegistry 仅实现
register/get/list/unregister/get_all_stats；未见
\_call_with_tracking、追踪器注入、权限注入等实现。

修正建议：二选一：A) 在 BaseTool
增加统一的执行封装（权限检查/追踪/超时/错误捕获/统计），并在
ToolRegistry.register() 中注入依赖；B) 将 tools/index.md
中未实现部分降级为["]{dir="rtl"}路线图/仅文档"，避免误导。

验证方法：若选择 A：为任意 Tool 调用建立统一 wrapper，并通过 1-2
个单测验证权限拒绝/统计增长/错误捕获一致；若选择
B：文档显式标注["]{dir="rtl"}未实现"。

TOOL-PERM-001（高）

来源文档：aiPlat-core/docs/tools/index.md

设计声明：PermissionManager
数据结构应保持单一、可预测的索引方式；grant/check 的读写路径应一致。

判定：❌不一致

问题类型：实现不合理/潜在缺陷

代码/文档证据：

code \| aiPlat-core/core/apps/tools/permission.py \| grant_permission()
写入 self.\_permissions\[key\]（user_id:tool_name）与
self.\_permissions\[user_id\]；但 check_permission() 仅读取
self.\_permissions\[user_id\]\[tool_name\]，导致前者写入无意义且污染结构。

修正建议：移除 self.\_permissions\[key\]
这一层写入，统一为：self.\_permissions\[user_id\]\[tool_name\] →
PermissionEntry；并补充 get_tool_users() 遍历逻辑以避免把非 user_id
键当作 user_id。

验证方法：增加单测：grant → check 必须为 True；revoke 后为
False；get_stats 的 total_users/total_entries 与实际授权数量一致。

INFRA-OBS-001（中）

来源文档：aiPlat-infra/docs/observability/index.md

设计声明：若文档宣称基于
OpenTelemetry（exporter/endpoint/propagators），代码应接入真实 OTel SDK
或明确标注为["]{dir="rtl"}简化实现/模拟实现"。

判定：❌不一致

问题类型：文档漂移/实现降级未披露

代码/文档证据：

doc \| aiPlat-infra/docs/observability/index.md \| 文档描述
OpenTelemetry tracing/metrics/logging，并包含 otlp/jaeger/zipkin 等
exporter 配置示例。

code \| aiPlat-infra/infra/observability/tracing.py \| 实现为
SimpleTracer/SimpleOTelMetrics/SimpleOTelLogger（内存对象），无 OTel
SDK/exporter/上下文传播实现。

code \| aiPlat-infra/infra/observability/factory.py \|
create_observability() 直接返回 Simple\* 实例字典，未接入 exporter。

修正建议：明确定位：若当前是["]{dir="rtl"}最小可用模拟实现"，在 docs
中标注并说明缺失项；若目标是真实 OTel，接入 opentelemetry-sdk 并实现
exporter/propagators 与配置加载。

验证方法：若接入 OTel：启动服务后可观察到 trace/span 导出（本地
collector 或 stdout exporter）；若保持简化：文档明确写["]{dir="rtl"}非
OTel 实现，仅提供抽象接口"。

INFRA-DI-001（中）

来源文档：aiPlat-infra/docs/di/index.md

设计声明：DI 模块若宣称支持 config 扫描、拦截器、auto_wire/strict_mode
等，应在容器实现或工厂层体现配置加载与行为差异。

判定：❌不一致

问题类型：文档漂移/功能未落地

代码/文档证据：

doc \| aiPlat-infra/docs/di/index.md \| 文档给出
config/infra/default.yaml 的 di.container.scan_packages、interceptors
等配置结构，并描述生命周期与作用域。

code \| aiPlat-infra/infra/di/container.py \| DIContainerImpl 未使用
DIContainerConfig 的 scan_packages/strict_mode/default_lazy
等字段；无扫描与拦截器机制；实例创建主要基于 inspect.signature
的注解解析。

code \| aiPlat-infra/infra/di/factory.py \| create_container() 仅 new
DIContainerImpl(config)，未见读取 yaml 或按 config 驱动的注册/扫描流程。

修正建议：将 docs 的["]{dir="rtl"}配置驱动
DI"与实现对齐：要么实现扫描与拦截器并接入配置加载，要么把 docs
中高级能力标注为规划项，避免让使用者误以为可用。

验证方法：新增示例/测试：配置 scan_packages
后可自动注册；拦截器（logging/metrics/error_handling）在 resolve/execute
链路中生效。
