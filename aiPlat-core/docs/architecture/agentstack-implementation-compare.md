# aiPlat vs Hermes vs Claude Code vs OpenClaw：核心实现与使用方式对照（基于代码结构）

> **v2.0 · 2026-06-16 更新**：新增 10 个 aiPlat 独有能力维度（§8），汇总表从 7 维扩展至 17 维。原始版本 2026-04-20。

> 范围：核心系统（≈Harness/“操作系统”）、Agent、Skill、MCP、Tool、提示词工程、上下文管理、知识库、代码智能、诊断、治理、学习教练、Sandbox、图表、记忆、人设、Ponytail
> 方法：以你当前 aiPlat 代码的“真实调用链/模块边界”为主轴，映射到三套开源标杆系统的对应机制，并给出“实现差异 + 使用差异 + 可吸收点”。

---

## 1. 核心系统（aiPlat 的 Harness / “操作系统”）对照

### 1.1 aiPlat：Harness 的职责边界与调用链（实现）

**关键特征：把 LLM/Tool/Skill/Exec 统一抽象为 syscalls，并通过 Gate/ContextVar 形成不可绕过的“内核面”。**

- **入口形态（使用）**：API 驱动（`core/server.py` → `Integration.execute`），而不是 CLI 主循环。
- **执行内核（实现）**：
  - `core/harness/integration.py`：把一次请求拆成 `kind=agent/skill/tool/...` 的执行分支；负责 trace_id/run_id、run_events、syscall_events、workspace/request 上下文设置。
  - `core/harness/kernel/execution_context.py`：基于 `contextvars` 的“内核态上下文”（ActiveRequest/Workspace/Release 等），下游 syscalls 自动读取。
  - `core/harness/syscalls/*.py`：syscall 适配层（LLM、Tool、Skill、File、Exec…）——是你系统里最接近“OS syscall 表”的位置。
  - `core/harness/execution/loop.py`：ReAct 风格 loop（`BaseLoop/ReActLoop`），内部用 `sys_llm_generate/sys_tool_call/sys_skill_call` 完成 Reason→Act→Observe。

**近似调用链（简化）**

```text
HTTP API (core/server.py)
  -> Integration.execute (core/harness/integration.py)
     -> set_active_*_context (execution_context.py)
     -> (optional) LearningApplier.resolve_active_release (core/learning/apply.py)
     -> sys_* (core/harness/syscalls/*)
        -> Gate: policy/approval/context/resilience（通过 syscalls + execution_context 统一生效）
        -> 真正执行（tool/skill/llm/exec）
     -> append run_events / syscall_events (ExecutionStore)
```

### 1.2 Hermes：对应的是“单体 Agent Loop + Tools Runtime”

Hermes 的“内核”不是 syscall 抽象，而是 **`run_agent.py` 里的 `AIAgent` 单体 loop**：prompt 构造→调用模型→解析 tool_calls→dispatch→写 session/压缩。  
工具执行通过 **Tool Registry/Toolsets**（`tools/registry.py` + `model_tools.py`）完成，属于 “agent loop 内置 runtime”。  
它更像“单进程虚拟机”，而你的 aiPlat 更像“有清晰 syscall ABI 的微内核”（并且跨 UI/API/Job 都复用）。

### 1.3 Claude Code：对应的是“Tool Execution Engine + Permission Layer + Sandbox”

Claude Code 把核心边界放在 **工具执行层**：FileRead/Write/Edit、Bash、Task、MCP wrapper 等都是一等工具；工具执行必须经过 PermissionClassifier/规则系统；并可在 Linux sandbox/seccomp 中执行 bash。  
它的“OS感”来自：**工具是 typed class** + **权限判定** + **沙箱约束**，而不是你们这种 “syscalls + Gate + run/syscall 事件化”。

### 1.4 OpenClaw：对应的是“Gateway 控制平面 + Pi Embedded Runner + Tool Policy/Exec Approvals”

OpenClaw 的内核是 **Gateway 侧的 run pipeline**：会话/多渠道→`runEmbeddedPiAgent`→工具组装（policy filter）→exec approvals（host run）→会话写入/compaction。  
它更像“Gateway OS”：强控制平面 + 受控工具生态；与 aiPlat 对齐点在于 **Tool Policy/Approval** 与 **host exec 风险控制**，差异在于你们更偏“平台 API + 可观测 run/syscall”。

---

## 2. Agent（实现 & 使用）对照

### 2.1 aiPlat Agent：loop 与 agent 类型解耦（实现）

你们的 Agent 体系是 **“IAgent 接口 + 可插拔 loop”**：

- 接口/数据结构：`core/harness/interfaces/agent.py`
- 基类：`core/apps/agents/base.py`
  - `BaseAgent.execute()` 负责：构造 `LoopState` → 注入 model/tools/skills → `self._loop.run()`
  - 支持 **暂停/恢复**：当 loop 返回 `PAUSED` 时会返回 `loop_state_snapshot`（用于下次 `_resume_loop_state` 恢复）
- ReAct Agent：`core/apps/agents/react.py`（本质是 BaseAgent + loop_type="react"）
- Multi-Agent：`core/apps/agents/multi_agent.py`
  - 组合多个 sub-agent，交给 Harness coordination patterns / langgraph（有并行、pipeline、supervisor、hierarchical delegation 等模式映射）

**使用差异（相对开源）**
- aiPlat：Agent 是平台资源（有 `/agents` 与 `/workspace/agents` 管理 API），并且会被 autosmoke、approval/policy、run_events 体系治理。
- Hermes/Claude Code：Agent 更多是“运行时实体/会话实体”，不是一个需要独立生命周期管理的“平台资源对象”（尽管 Claude 有 subagent、Hermes 有 delegate/subagent）。
- OpenClaw：Agent 更像“Gateway 下的 session runner”，侧重多渠道会话路由与工具/策略。

### 2.2 Hermes：AIAgent 单体 loop（实现/使用）

Hermes 的 Agent 核心是 `AIAgent`（单体 loop），支持：
- 多 API mode（OpenAI/Responses/Anthropic Messages）统一成 OpenAI 风格 message 结构
- tool_calls 并发执行（线程池）
- 子代理/委派（delegate tool）
- 会话存储（SQLite）+ 压缩 + prompt cache

> Hermes 的“Agent”更像 “一个可持续运行的对话进程”，而 aiPlat 的 “Agent”更像“平台可配置的执行模板 + loop runtime”。

### 2.3 Claude Code：Main Agent + Task Subagents（实现/使用）

Claude Code 以“主 agent + Task subagent”组织工作，子代理通常用于分工（review/feature-dev 等插件也利用多代理）。  
它强在 **开发者工作流**（worktree、IDE/CLI）与 **权限规则**，弱在“平台化 Agent 生命周期治理”（这正是你们方向）。

### 2.4 OpenClaw：Session-key 驱动的 agent run（实现/使用）

OpenClaw 的 agent run 是“会话级”（session_key），并且与 channel/group policy 强绑定；subagent 深度、工具 denylist 会随 spawn depth 收紧。

---

## 3. Skill（实现 & 使用）对照

### 3.1 aiPlat Skill：两套概念并存（很重要）

你们系统里有两层“Skill”概念：

1) **Harness loop 层的 Skills 列表**：`BaseAgent.execute()` 会把 `AgentContext.skills` 从 registry resolve 成 skill 实例并注入 loop（`core/apps/agents/base.py`）。

2) **管理平面/资源库的 Skill Manager**：`core/management/skill_manager.py`（你们用于 workspace/engine、版本、回滚、发布的那套），并且与你们“自进化闭环”已打通（candidate publish 可 materialize workspace skill version）。

另外还有一个 **内存态 SkillRegistry**：`core/apps/skills/registry.py`
- 具备版本列表与 `rollback_version()`（会把 config 回写到 skill 实例）
- 具备 enable/disable、绑定统计

> 结论：aiPlat “Skill”更像“平台资源（可版本/可回滚/可灰度） + 运行时注入（loop 执行依赖）”，而不是简单的 prompt snippet。

### 3.2 Hermes Skills：prompt 注入为主 + tool 扩展为辅

Hermes 的 skills 更偏“能力包/提示词+工具配置”，加载后会影响系统 prompt（skills index）和可用工具集。  
它强调“自进化/迭代”（learning loop）和“个人助手风格可变人格”，但工程化发布/灰度/回滚通常不如你们严格。

### 3.3 Claude Code Skills：SKILL.md + 插件生态

Claude Code 的 skills 通过 `SKILL.md` 作为规范入口（并可被插件提供），且可以限制 skill 内联 shell 执行（安全项）。  
它强在插件市场与 IDE/CLI 的“技能产品化分发”，但不天然提供“技能发布灰度 + run 级审计闭环”。

### 3.4 OpenClaw Skills：system prompt 中的 Skills section + 安装/状态

OpenClaw 在 `buildAgentSystemPrompt()` 中把 skills 作为模块化 section 注入，且与 workspace bootstrap files、prompt mode（full/minimal）联动。  
它更像“可携带的能力套件”，而 aiPlat 更像“平台内可治理资产”。

---

## 4. Tool（实现 & 使用）对照

### 4.1 aiPlat Tool：类接口 + 统一 wrapper（实现）

- BaseTool：`core/apps/tools/base.py`
  - 统一：参数校验 →（可选）permission check → timeout/异常 → stats
  - 支持 tracer span（`tool.<name>`）
- ToolRegistry：你们有注册表（在 `apps/tools` 内通过 `get_tool_registry()` 使用；同时 MCPRuntime 会向 registry 动态注册）
- Harness syscalls：loop 并不直接调用 tool.execute，而是走 `sys_tool_call`（统一 Gate/审批/策略/审计）

**使用上**：一个 Tool 是“平台能力”，可以被 policy/approval gate 管控，并在 run/syscall 事件中可追溯。

### 4.2 Hermes Tool：函数注册 + toolset 组合（实现）

Hermes tools 通过 `registry.register(...)` 在 import 时自注册；toolset 决定哪些工具暴露给模型；tool_calls 可以并发执行。  
优势：生态与扩展成本低（Python 函数即工具）。  
弱点（对你们平台化而言）：治理/审计需要额外体系（Hermes 有 session DB，但你的 run/syscall 事件化更偏生产运营）。

### 4.3 Claude Code Tool：typed tools + permission rules（实现）

Claude Code 工具是“强类型类”（BashTool/FileWriteTool/TaskTool/MCP wrapper 等），每个 tool call 都要经过 PermissionChecker（managed/user/local settings + 交互审批）。  
它的治理更偏“端侧/企业策略”，你的治理更偏“平台控制平面 + 证据链”。

### 4.4 OpenClaw Tool：tool assembly + policy filtering + exec approvals（实现）

OpenClaw 在每次 run 前组装工具数组（AnyAgentTool），做：
1) schema normalization（不同 provider 兼容）
2) tool policy filter（global/agent/profile/group/subagent depth）
3) guardSessionManager（防 tool result 污染 transcript）
4) exec approvals（host run 风险）

> OpenClaw 最接近你们“policy/approval + runtime tool filtering”的设计，但它的控制平面是 Gateway 会话/频道驱动；你们是 API/平台驱动。

---

## 5. MCP（实现 & 使用）对照

### 5.1 aiPlat MCP：MCPRuntime 把 server 变成 ToolRegistry 工具（实现）

关键文件：`core/apps/mcp/runtime.py`

- `MCPRuntime.sync_from_servers(servers, tool_registry)`
  - 遍历 enabled servers：connect + register server tools
  - server 的 tools 会以 `mcp.<server>.<tool>` 的形式注册进 ToolRegistry
- 重点：**在连接/注册前先做 policy 评估**
  - `evaluate_mcp_server(...)`（tenant/actor 维度）返回 DENY 时会写 syscall_event（best-effort）
  - 生产环境对 `stdio` 有默认 deny（除非 policy.prod_allowed=true）

**使用差异**
- 你们的 MCP 是“平台内工具的一部分”：能纳入 policy/approval、能落 syscall_event、能做 prod 安全默认。
- 且你们有 engine/workspace 两套 MCPManager（server.py 里 `_sync_mcp_runtime()` 将两边 server 聚合后 sync）。

### 5.2 Hermes MCP：discover_mcp_tools → register 到同一 registry（使用）

Hermes 在 tool discovery 后，会发现 MCP servers 并注册 MCP tools 到 registry；工具与内建工具统一暴露给模型。

### 5.3 Claude Code MCP：mcp-servers.json + MCPSearch（规模优化）

Claude Code 的 MCP 亮点是“工具描述过大时的动态发现”：当 MCP tool descriptions 占用 context > 阈值，会使用 MCPSearch 做按需注入，避免一次性塞满上下文；并支持 stdio/SSE/HTTP/WS 多 transport。

### 5.4 OpenClaw MCP：作为 tool sourcing 的一种模式（并受 tool policy 管控）

OpenClaw 把 MCP 作为 tool sourcing/扩展的一部分（与 plugins、LSP 等并列），并且受 tool policies 过滤；subagent depth 也会影响可用工具。

---

## 6. 提示词工程（Prompt Engineering）对照

### 6.1 aiPlat：PromptAssembler + 发布/灰度/学习补丁（实现）

你们的 prompt 工程与“平台治理”结合更紧：
- Prompt 组装：`core/harness/assembly/prompt_assembler.py` + `context_assembler.py`
- 请求级上下文：来自 `execution_context`（tenant_id、actor_id、toolset、active_release 等）
- 你们已把 **prompt_revision patch** 做成“可发布候选 + rollout + 回滚”，并在运行时通过 `LearningApplier` 注入（我们刚把 active_release 挂到了 tool/skill 级执行）

**使用体验**：提示词是可运营资产（版本/灰度/回滚/审计），不是单纯工程文件。

### 6.2 Hermes：cached system prompt vs ephemeral additions（强缓存导向）

Hermes 明确区分：
1) 可缓存的稳定 system prompt layers（identity/memory/skills/context files…）
2) API call 时的 ephemeral additions  
目的：最大化 provider prompt cache 命中、保持会话语义稳定。

### 6.3 Claude Code：围绕工具与会话的 prompt 组织

Claude Code 的 prompt 组织与 compaction、工具描述大小、权限提示强耦合；并通过 hooks/plugins 改写行为。

### 6.4 OpenClaw：buildAgentSystemPrompt（full/minimal/none）+ workspace bootstrap 注入

OpenClaw 的 prompt 工程最大特征是：
- prompt mode（full/minimal/none）按 session 类型切换（subagent/cron 默认 minimal）
- 自动注入 workspace bootstrap 文件（agents.md/soul.md/tools.md/memory.md…），并做 budget/truncation
- 做 prompt normalization 来提升 cache stability

> 你们可以吸收 OpenClaw 的“prompt mode + bootstrap 文件注入预算控制”，用于降低平台长会话的 token 波动。

---

## 7. 上下文管理（Context Management）对照

### 7.1 aiPlat：两层上下文

1) **内核态上下文（contextvars）**：`execution_context.py`  
   - ActiveRequestContext（tenant/actor/session/toolset/…）
   - ActiveWorkspaceContext（workspace_id/skill scope/…）
   - ActiveReleaseContext（candidate/version/summary）
   - PromptRevisionAudit（记录本次 request 应用了哪些 patch、冲突等）

2) **对话/运行上下文（LoopState.context/messages/history）**：`core/harness/execution/loop.py`  
   - 有非常“工程化”的控制：`_apply_observability_control()` 在 token ratio > 0.8 时做极简 compaction（保留最后 2 条）；tool error rate 高时 PAUSE（需要人工介入）

此外你们还有 **执行级持久化**：
- run_events / syscall_events / agent_history（ExecutionStore）用于审计与回放，而不是为了“对话持续性”本身。

### 7.2 Hermes：Session DB + 压缩（保 last N + lineage）+ memory flush

Hermes 侧重点是长期对话的“连续性与成本”：
- 会话存 SQLite
- 压缩会产生 lineage（父子 session）
- 保留 protect_last_n，且 tool call/result 成对保留

### 7.3 Claude Code：token tracking + auto compaction（~98%）+ 状态保留

Claude Code 的 compaction 很强：会保留 plan mode、session name、hook context、subagent history 等元信息；并对 tool output / MCP result size 有专门策略。

### 7.4 OpenClaw：compaction + transcript repair + tool result guard

OpenClaw 的 compaction 在工程细节上非常“硬”：
- session file write lock
- tool result pairing repair（避免孤儿 tool result）
- strict identifier preservation（避免 summary 丢 UUID/文件名）
- guardSessionManager（防止模型伪造 tool result 注入 transcript）

> 你们若要做“平台级长会话”，OpenClaw 的 transcript repair/guard 思路很值得吸收；你们当前更偏“每次执行可追溯”，而不是“超长会话一致性”。

---

## 8. aiPlat 独有能力维度（其他三系统无对应机制）

> 以下 10 个维度是 aiPlat 2026-04 至 2026-06 期间新增的能力，Hermes、Claude Code、OpenClaw 均不具备等价机制。这些能力使 aiPlat 从"Agent Runtime"升级为"可运营的 AI 平台"。

### 8.1 知识库 / Wiki 本体系统

**核心文件**：`core/harness/knowledge/wiki_engine.py`、`wiki_health_rules.py`、`knowledge_abox_builder.py`

- **Wiki 页面管理**：30 页面 + 全文检索 + 双向链接 + 死链/孤立检测
- **T-Box / A-Box 本体**：774 triples，15 条 Golden 回归，100 分本体健康评分
- **自动原子化**：LLM 从长文/视频中提取 `KnowledgeAtom`，含 evidence_text / source_doc_id / confidence 溯源
- **策展管线**：`POST /wiki/curate` 并行策展（asyncio.gather BATCH=5），LLM 裁剪输入到 4000 字符
- **健康检查**：11 项自动检查（重复/死链/孤立/过短/本体一致性/语义矛盾），前端 `WikiHealthDashboard`
- **视频入库**：`_load_elements_from_kb()` 从 kb_elements 表直读，绕过 dispatch 表限制
- **跨模态**：`refersToImage/refersToTable/explains/belongsToSection` 关系抽取

> 对比：Hermes 有 session-based conversation history；Claude Code 有 project-level context files。两者都没有结构化的知识本体系统。

### 8.2 代码智能图谱（Cross-Language Code Graph）

**核心文件**：`core/harness/syscalls/code_intel.py`、`graphs/code_graph.py`

- **规模**：96,433 节点 + 99,000+ 边，覆盖 Python + TypeScript 全栈
- **跨语言链路**：28 条跨栈边（前端 fetch → 后端路由 → handler）
- **框架感知路由**：AST 解析 91 条 FastAPI `@router`→handler + React 路径→组件映射
- **继承关系**：487 条继承边 + `sys_code_intel_subclasses` 工具
- **领域视图**：13 个业务域标注，`SystemGraph` 五 Tab 前端展示
- **4 个 syscall 工具**：`sys_code_intel_context`、`sys_code_intel_blast`、`sys_code_intel_callers`、`sys_code_intel_affected`
- **导出**：JSON 提交导出 + 专用 tour API 端点

> 对比：Claude Code 有 project-level 代码理解但无持久化图谱。Hermes/OpenClaw 无此概念。aiPlat 的图谱是**持久化的、可查询的、跨语言的平台资产**。

### 8.3 统一诊断中心 + 架构守卫

**核心文件**：`scripts/architecture_guard.sh`、`tests/constitution/`、`core/api/routers/diagnostics.py`

- **架构守卫**：15 维检查矩阵（导入方向/职责归属/内核无关/基础设施独立/门面使用/接线完成/前端代理路由/子进程 Python 一致性/跨语言 API 契约/MCP 冒烟测试/模型解析集中化/提示词模板管理/Skill 执行真实性/接线完成度标记/Agent 边界）
- **诊断检查**：断链检测 + 死代码扫描 + 路由验证 + 耦合指标 + 能力图谱入口重复扫描
- **性能优化**：共享代码图谱（6→1 次调用）、`_DIAG_CACHE` 加 TTL、quick 模式跳过慢检查
- **前端**：`/diagnostics` 统一面板 + per-item detail with links + 架构守卫 UI 一键运行
- **CI 集成**：`.github/workflows/aiplat-contracts-guard.yml`

> 对比：Claude Code 有 permission rules checker；OpenClaw 有 tool policy filter。两者都没有像 aiPlat 这样的**15 维全栈架构守卫 + 诊断闭环**。

### 8.4 治理审批全闭环

**核心文件**：`core/policy/`、`core/harness/gates/`、`core/harness/execution/assess_agent.py`

- **PolicyGate 实时拦截**：`sys_file_write`/`sys_file_edit` 执行前检查目标路径架构边界（非 core 层写 core → DENY）
- **字段级脱敏**：`field_level_security.py` 单元格级别 redaction
- **Per-object RBAC**：`object_permission.py`，RBAC→Marking→ObjPerm 三层现算
- **独立 AssessAgent**：只评分不修改 + 反借口表（7 条 Rationalizations 自动辩驳）
- **异常处理增强**：LLMResult 结构化返回（truncated / finish_reason / error_type）
- **安全闭环**：`_guard_messages()` 6 条注入检测正则 + 特殊 token 过滤 + safety_audit 日志

> 对比：Claude Code 有 PermissionClassifier（工具级）；OpenClaw 有 tool policy filter（会话级）。aiPlat 的治理是**三层架构边界 + 字段级 + 实时拦截**，颗粒度远更细。

### 8.5 AI 学习教练 (L1-L6)

**核心文件**：`core/harness/knowledge/learning_coach.py`、`assessment_engine.py`

- **学习域 T-Box**：8 个新类（LearningPath、Chapter、Exercise、Assessment 等）
- **3 条内置路径**：19 章 + 26 道习题
- **评估引擎**：MC 自动判分 + LLM 开放评估 + 三层降级（LLM→规则→待重评队列）
- **双向写入**：mastery→A-Box（知识图谱反馈学习成果）
- **知识盲区检测**：5 维检测（频率/难度/关联/时间/置信度）+ 注入 Agent prompt

> 对比：Hermes 有 learning loop（agent 自进化）。aiPlat 的学习教练是**面向人类用户的、结构化的教学系统**，与 agent 自学习是完全不同的维度。

### 8.6 Pipeline Sandbox + 部署闸门

**核心文件**：`core/harness/execution/pipeline_sandbox.py`、`pipeline_engine.py`

- **场景合成**：从已有 PipelineStageConfig 批量生成变体场景
- **10 种突变**：参数扰动 / 顺序交换 / 阶段插入 / 阶段删除 / 超时缩限 / 资源限制 等
- **批量验证**：sandbox 中并行跑全部变体，输出 pass/fail 矩阵
- **部署闸门**：`/pipeline/ship` — assess → security → sandbox → perf → notes 五步审批
- **失败聚类**：三维归因（verifier / causal / mechanism）+ 回放版本化（tbox_hash）

> 对比：Claude Code 有 workflow testing；OpenClaw 有 subagent testing。aiPlat 的 sandbox 是**系统化的流水线压力测试 + 部署前审批闸门**。

### 8.7 图表生成（Draw.io 内置）

**核心文件**：`core/harness/syscalls/drawio_gen.py`

- **零外部依赖**：LLM 直接输出 Draw.io XML，前端 `viewer.diagrams.net` 嵌入渲染
- **本地存储**：图表落 `~/.aiplat/diagrams/`
- **前端页面**：管理端 `Diagrams` 页面 + 导航入口

> 对比：没有任何对比系统有内置图表生成。它们需要外部 MCP 或手动操作。

### 8.8 跨会话 / 共享记忆

**核心文件**：`core/harness/memory/cross_session.py`、`shared_memory.py`、`profile_builder.py`

- **跨会话记忆**：自动读取最近 5 个 `SESSION_NOTES.md`，注入当前会话上下文
- **共享记忆**：跨 Agent 实例 `collective_learnings` 池，SQLite 持久化
- **L3 事实自动提取**：对话中检测"预算/名字/目标"声明 → 自动更新 User Profile
- **Profile Builder**：Hermes 风格的 `run_agent.py:2423-2456` 设计原则映射

> 对比：Hermes 有 session DB + memory flush；Claude Code 有 CLAUDE.md（永不压缩）。aiPlat 在此基础上加了**跨会话+共享记忆的层次**。

### 8.9 Skill Chain + 人设系统

**核心文件**：`core/apps/skills/`、`~/.aiplat/skills/`

- **Skill Chain**：`skill_chain: [dep1, dep2]` 声明式依赖，Agent 自动解析
- **3 个 Agent 人设**：security-auditor / test-engineer / web-perf-auditor，带完整 SOP 和工具集
- **反借口表**：7 条 Rationalizations 自动辩驳（"这个太复杂了" → "复杂度不是借口"）
- **渐进式暴露**：skill stubs ~50 tokens/skill，展开后完整注入
- **后台策展**：`_bg_curator_scan` 每 6 小时扫描新 skills
- **导入端点**：GET/POST/DELETE on `/skills/install-from-directory` + 前端 ImportBar "本地目录"模式

> 对比：Claude Code 有 SKILL.md + 插件。aiPlat 多了**依赖链、人设系统、反借口表、自动策展**。

### 8.10 Ponytail 模式（Lazy Senior Developer）

**核心文件**：`~/.aiplat/skills/ponytail-lazy/`、环境变量 `PONYTAIL_MODE`

- **6 阶决策阶梯**：off → lite → full → ultra，每阶增加更多自检和审慎
- **纯 Prompt 工程**：SKILL.md 注入，不修改模型路由
- **环境变量控制**：`PONYTAIL_MODE` (off/lite/full/ultra)，按任务类型切换
- **行为验证通过**：off/full/ultra 三种模式行为差异符合预期

> 对比：Claude Code 有 plan mode。aiPlat 的 Ponytail 更细粒度（4 级），且完全通过 prompt 工程实现，不需修改核心代码。

---

## 9. 汇总对照表（更新至 2026-06）

| 维度 | aiPlat（你的系统） | Hermes | Claude Code | OpenClaw |
|---|---|---|---|---|
| **基础维度** | | | | |
| 核心内核形态 | **syscalls + Gate + execution_context（像 OS ABI）** | 单体 Agent Loop（像 VM） | Tool Engine + Permission + Sandbox | Gateway + Pi Runner + Tool Policy/Exec Approvals |
| Agent | IAgent + 可插拔 loop；Agent 作为平台资源 | AIAgent 主循环；会话即 agent | Main agent + Task subagents | session_key 驱动 run；subagent depth 收紧 |
| Skill | 平台资产（workspace/engine）+ runtime 注入；可版本/回滚/灰度 + skill_chain + 人设 | prompt/能力包；偏自进化 | SKILL.md + 插件生态 | prompt section + 安装/状态；偏 portable |
| Tool | 类接口 + sys_tool_call；可审计（run/syscall） | 函数注册 + toolset | typed tools + 规则权限 | tool assembly + policy filter + guard |
| MCP | MCPRuntime 注册为 `mcp.<server>.<tool>`；prod 安全默认 + EventBus/SSE 测试 | MCP tools 注册进 registry | mcp-servers.json；MCPSearch 动态发现 | MCP 作为 tool sourcing；受 policy 过滤 |
| 提示词工程 | PromptAssembler + 发布灰度 + learning patch + prompt_loader 模板化（强治理） | cached prompt layers + ephemeral | 围绕工具/会话/权限+compaction | prompt modes + bootstrap 注入 + normalization |
| 上下文管理 | contextvars（内核态）+ LoopState（执行态）+ run/syscall 事件化 + 跨会话/共享记忆 | session DB + 压缩 + memory | token tracking + auto compaction（~98%） | compaction + transcript repair + guard |
| **aiPlat 独有维度** | | | | |
| 知识库/Wiki 本体 | ✅ T-Box/A-Box 本体 + 自动原子化 + 健康检查 + 策展 + 视频入库 + 跨模态 | ⸺ | ⸺ | ⸺ |
| 代码智能图谱 | ✅ 96K 节点跨语言图谱 + 框架感知路由 + 继承图 + syscall 工具 | ⸺ | ⸺ | ⸺ |
| 统一诊断中心 | ✅ 15 维架构守卫 + 断链/死代码/路由/耦合检测 + 前端面板 | ⸺ | ⸺ | ⸺ |
| 治理审批全闭环 | ✅ PolicyGate 实时拦截 + 字段级脱敏 + per-object RBAC + AssessAgent | ⸺ | ⸺ | ⸺ |
| AI 学习教练 | ✅ L1-L6 学习域 T-Box + 3 条路径 + 评估引擎 + mastery→A-Box | ⸺ | ⸺ | ⸺ |
| Pipeline Sandbox | ✅ 场景合成 + 10 种突变 + 批量验证 + /pipeline/ship 部署闸门 | ⸺ | ⸺ | ⸺ |
| 图表生成 | ✅ LLM→Draw.io XML + viewer.diagrams.net 前端渲染（零外部 MCP） | ⸺ | ⸺ | ⸺ |
| 跨会话/共享记忆 | ✅ SESSION_NOTES + collective learnings + L3 事实自动提取 | ⸺ | ⸺ | ⸺ |
| Skill 人设系统 | ✅ 3 个人设 + 反借口表 + skill_chain + 后台策展 + 导入端点 | ⸺ | ⸺ | ⸺ |
| Ponytail 模式 | ✅ 6 阶决策阶梯 + Prompt 工程驱动 + 环境变量控制 | ⸺ | ⸺ | ⸺ |


---

## 10. 吸收点建议（按你们平台定位）

1) **从 Claude Code 吸收：MCP 规模化与权限 UX**  
   - 类似 MCPSearch 的“按需注入 tool schemas”，避免你们 MCP server 多时 tool 描述膨胀。  
   - 权限决策的“可重试/可提示替代方案”的交互（他们有 PermissionDenied hook retry）。

2) **从 OpenClaw 吸收：长会话一致性与 transcript 防腐**  
   - tool result pairing repair / session guard（防止上下文被 tool result 异常破坏）  
   - compaction 的 identifier preservation（防 UUID/文件名丢失导致不可复现）

3) **从 Hermes 吸收：prompt 缓存稳定性设计**  
   - cached system prompt vs ephemeral overlay 的明确分层（有助于降低 token 成本与波动）  

---

## Sources（外部系统参考）

- Hermes：Agent loop / Prompt assembly / Tools runtime  
  - https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop  
  - https://hermes-agent.nousresearch.com/docs/developer-guide/prompt-assembly  
  - https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime
- Claude Code：Tool system / Context compaction / MCP integration  
  - https://deepwiki.com/anthropics/claude-code/3.2-tool-system-and-permissions  
  - https://deepwiki.com/anthropics/claude-code/3.3-context-window-and-compaction  
  - https://deepwiki.com/anthropics/claude-code/3.5-mcp-server-integration
- OpenClaw：Tools system / Tool policy / System prompt / Context compaction  
  - https://deepwiki.com/openclaw/openclaw/3.4-tools-system  
  - https://deepwiki.com/openclaw/openclaw/3.4.1-tool-policies-and-filtering  
  - https://deepwiki.com/openclaw/openclaw/3.2-system-prompt-and-context  
  - https://deepwiki.com/openclaw/openclaw/3.6-context-compaction

