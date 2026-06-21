# aiPlat vs Hermes vs Claude Code vs OpenClaw：17 维度代码级对比分析 v3.0

> **v3.0 · 2026-06-16 更新**：维度从 7 扩展到 17，分析数据来源为 aiPlat 自有的代码智能图谱（1,257 文件 / 20,103 边）和能力图谱（172 节点 / 140 边）的实时导出数据，Hermes/Claude Code 侧来自其最新官方技术文档的代码级描述。
>
> **数据来源**：
> - aiPlat：`code_graph.db` (1,257 文件, 992 Python + 262 TypeScript) + `cap_graph.db` (45 agents, 61 skills, 35 tools)
> - Hermes：`hermes-agent.nousresearch.com` 开发者文档 (Agent Loop / Prompt Assembly / Tools Runtime)
> - Claude Code：`deepwiki.com/anthropics/claude-code` 源码分析 (Tool System / Context Compaction / Hook System)

---

## 基础面 (Dimensions 1-5)

### 1. 执行核心 (Execution Core)

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **主文件** | `run_agent.py` `AIAgent` 单体类 (~3,000 行) | Task Engine + Agent loop | `loop.py` `BaseLoop/ReActLoop` (2,791 行) + `integration.py` (3,340 行) |
| **代码形态** | 单体 while 循环 | Agent 自循环 + Task 委托 | **微内核**：Integration 拆 kind=agent/skill/tool 分支 + Loop 分层执行 + 4 层 Gate |
| **入口** | `agent.chat()` / `agent.run_conversation()` | CLI `/command` → Task dispatch | `Integration.execute()` → `set_active_*_context` → syscall 表 |
| **循环模型** | `build prompt → LLM → parse tool_calls → dispatch → loop` | Reason→Act→Observe 隐含 | **显式 ReAct**：`_reason()` → `_act()` → `_observe()`，每步可被 Hook 拦截 |
| **中断/恢复** | `_interruptible_api_call()` 线程信号 | Task 级完成通知 | **完整 PAUSE/RESUME**：`loop_state_snapshot` → 下次 `_resume_loop_state` |
| **模块规模** | `run_agent.py` 单文件 | 闭源，无公开数据 | 16 个执行模块 (loop/integration/engine/pipeline) |
| **状态管理** | `conversation_history: list[dict]` | Session state dict | **双层**：`contextvars` 内核态 + `LoopState` 执行态 |

**核心差异**：Hermes 是单文件单进程 VM。aiPlat 是微内核 ABI，Integration 解耦入口，Loop 分层执行，Gate 统一拦截。

---

### 2. 工具系统 (Tool System)

> 代码规模：aiPlat 24 个 tool/syscall 模块，35 个注册工具

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **注册方式** | `registry.register(name, handler, schema)` 导入时自注册 | Typed class：`FileReadTool`/`BashTool`/`FileWriteTool` | **双轨**：`BaseTool` 类接口 + `ToolRegistry` 单例 |
| **发现** | AST 扫描 `tools/*.py` → `importlib.import_module` | 编译时注册 + MCP 动态发现 | `get_tool_registry()` + MCPRuntime 注册为 `mcp.<server>.<tool>` |
| **调用路径** | `handle_function_call()` → `registry.dispatch()` → 直接调 handler | Tool Engine → PermissionClassifier → Sandbox → 执行 | **syscall ABI**：`sys_tool_call()` → `PolicyGate.check_tool()` → `TraceGate` → `ContextGate` → `ResilienceGate` |
| **权限控制** | `DANGEROUS_PATTERNS` 正则 (rm -rf/mkfs/DROP TABLE) | **三级规则**：deny/ask/allow + Managed>User>Local 层级 | **四层 Gate**：PolicyGate(permission+approval) / TraceGate(span+audit) / ContextGate(resource) / ResilienceGate(timeout/retry) |
| **工具数量** | ~30+ 内置 | 10+ typed tools | 35 个注册工具 + MCP 动态扩展 |
| **错误包装** | 两层 try/except 返回 JSON error | PermissionDenied/prompt | `ToolResult` 结构化 (success/error/approval_required) |
| **并发** | 单 tool 串行，多 tool 线程池并发 | 主 agent 串行，subagent 并行 | Loop 内 syscall 串行，Integration 可并行多个独立 run |

**核心差异**：aiPlat 的工具调用是不可绕过的 syscall ABI——所有 tool 必经 `sys_tool_call` → 四层 Gate → 事件记录。Hermes 的 `handle_function_call()` 是 agent loop 内直接 dispatch。Claude Code 的 PermissionClassifier 工具粒度更细但不如 aiPlat 系统化。

---

### 3. 上下文与压缩 (Context & Compaction)

> 代码规模：aiPlat 23 个 memory/context 模块 (harness/memory/ 13 + harness/context/ 4 + harness/assembly/ 4 + harness/restatement/ 2)

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **压缩触发** | 50% 预检，85% 网关自动压缩 | ~98% 自动触发 | **6 级渐进**：NORMAL(<70%) / WARNING(70-80%) / REPLACE(80-85%) / PRUNE(85-90%) / AGGRESSIVE(90-99%) / EMERGENCY(≥99%) |
| **压缩策略** | 中间轮次摘要 + 保留最后 20 条 | 剥离图片/PDF → LLM 摘要 → 保留 meta | **priority 排序**：low 先删，high 保留，medium 压缩为摘要 |
| **不压缩项** | tool call/result 成对，最后 N 条 | plan mode, session name, hook context, crons | **CLAUDE.md 永不压缩**：每次 LLM 调用从磁盘重读 |
| **会话持久化** | SQLite `hermes_state.py` | Session file + model 保持 | `ExecutionStore`：run_events + syscall_events + agent_history 全量 |
| **上下文注入** | `ephemeral_system_prompt` 瞬态 | 每次 re-read CLAUDE.md | `_try_inject_claude_md()` + `_try_inject_arch_rules()` + `_try_inject_memory_reminders()` |

**aiPlat 优势**：6 级渐进 + priority 排序是最细粒度的压缩策略。CLAUDE.md 永不压缩是独特设计。

---

### 4. 提示词工程 (Prompt Engineering)

> 代码规模：aiPlat 15 个 prompt/assembly 模块

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **分层** | 3 层：stable (SOUL.md+skills) / context (AGENTS.md) / volatile (MEMORY.md+USER.md) | system + tools + permissions | **双层**：`PromptAssembler` (版本化) + `ContextAssembler` (请求级注入) |
| **缓存策略** | 分层分离最大化 provider cache 命中 | provider prompt cache | `stable_system_prompt` + `ephemeral_overlay` 分离，SHA-256 版本 |
| **上下文文件** | `.hermes.md`→`AGENTS.md`→`CLAUDE.md`→`.cursorrules` 优先级取 1 | CLAUDE.md 每次重读 | CLAUDE.md + `_try_inject_arch_rules()` 每次注入 |
| **治理** | 无 —— SOUL.md 编辑即生效 | 无 —— settings.json 编辑即生效 | **PromptAssembler + 灰度发布 + learning patch**：版本/灰度/回滚/审计 |
| **模板管理** | 无 | 无 | `prompt_loader` 统一注册 + `${var}` 占位符 + DB 覆盖 |

**核心差异**：Hermes/Claude Code 提示词是文件编辑即生效。aiPlat 把 prompt 做成可版本/可灰度/可回滚的平台资产。

---

### 5. 记忆系统 (Memory System)

> 代码规模：aiPlat 13 个 memory 模块 + SQLite FTS5 持久化

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **架构** | `MEMORY.md` + `USER.md` + session DB (SQLite) | CLAUDE.md (永不压缩) + session file | **四层**：Hot(Working, 30K deque) / Warm(Episodic, 规则摘要) / Cold(Semantic, SQLite FTS5) / External(Task Skills, JSON + SkillRegistry) |
| **持久化** | `hermes_state.py` SQLite + memory tool flush | 会话结束写 file | `MemoryManager.save_interaction()` → SQLite `long_term_memories` + FTS5 |
| **跨会话** | `session_search` tool → SQLite 跨 session 检索 | Session resume (`/resume`) | **自动注入**：最近 5 个 SESSION_NOTES + shared memory(跨实例) + L3 事实自动提取 |
| **过期** | 无 | 无 | `long_term_memories` 自动过期 |
| **晶体化** | 无 | 无 | Task Skills pass_rate≥85% → 自动注册 SkillRegistry |
| **注入时机** | volatile tier (snapshot at session start) | Session start | `_try_inject_memory_reminders()` 每轮注入 |

**核心差异**：四层模型来自 Hermes 启发 (`manager.py:9` 明确标注)，但 aiPlat 在工程实现上远超——跨会话自动注入、共享记忆、L3 事实提取、Skill 自动晶体化，这些都是 Hermes 没有的。

---

## 架构面 (Dimensions 6-8)

### 6. 部署与运维 (Deployment & Ops)

> aiPlat 部署相关模块：90 个 (server/api/routers)

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **部署形态** | 本地 CLI，单进程 (`hermes chat`) | 内嵌在 Claude 应用中 | **微服务架构**：FastAPI (core:8002) + management:8000 + platform:8003 + app:8004 + Vite:5173 |
| **启动方式** | `pip install` + `hermes chat` | Claude Desktop / CLI | `core/server.py` (1,916 行) + 多子进程 |
| **依赖管理** | pip + 单 requirements | 内嵌 | 多服务编排 + 容器化就绪 |
| **配置热更新** | 需重启 | 需重启 | **Gate 级动态配置** + hot_reload 事件驱动 |
| **多租户** | 无 | 无 | **有**：tenant 上下文隔离 (contextvars) |
| **服务数量** | 1 个进程 | 1 个进程 | 5 个独立服务进程 |
| **水平扩展** | 不支持 | 不支持 | 无状态 API → 可水平扩展 |

**核心差异**：aiPlat 是唯一的微服务架构，支持多租户、动态配置、水平扩展。其他三个都是单进程 CLI/桌面应用。

---

### 7. 可观测性 (Observability)

> 代码规模：aiPlat 35 个可观测性模块 (observability/ 5 + trace/event 相关 30+)

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **调用链追踪** | 无 | OTEL span (agent_id/parent_agent_id) | **TraceGate 完整 span**：每个 syscall 独立 span_id + parent_id |
| **事件审计** | 无结构化 | `tool_decision` telemetry events | **syscall_event + agent_history 全量**：ExecutionStore 持久化 |
| **成本追踪** | 无 | `/usage-credits` 命令 | **BudgetGate 实时 token/成本**：`token_usage/token_limit` 监控 |
| **调试能力** | print/日志 | 日志文件 | **loop_state 快照** + checkpoint 恢复 + `breakpoint()` 兼容 |
| **性能指标** | 无 | `context_window.used_percentage` | **四层 Gate 各自计时** + `_DIAG_CACHE` + quick mode |
| **诊断面板** | 无 | 无 | 统一诊断中心 + 15 维架构守卫 + 前端 dashboard |
| **代码图谱** | 无 | 无 | 1,257 文件 / 20,103 边实时查询 (blast/callers/affected) |

**核心差异**：这是 aiPlat 单方面碾压的维度。Hermes/Claude Code 只有基础日志，aiPlat 有全链路 TraceGate + 结构化事件 + 诊断面板 + 代码图谱四层可观测体系。

---

### 8. 安全与合规 (Security & Compliance)

> 代码规模：aiPlat 32 个安全模块 (policy/ + gate/ + security/)

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **提示注入防护** | `_scan_context_content()` 基础扫描 | 内建 | **`_guard_messages()` 6 条正则** + 特殊 token 过滤 + safety_audit 日志 |
| **危险命令检测** | `DANGEROUS_PATTERNS` 正则 (rm -rf/mkfs/DROP TABLE) | `rm -rf $HOME` 等阻止 | PolicyGate 架构边界拦截 (非 core 层写 core → DENY) |
| **敏感信息脱敏** | 无 | 基础 | **字段级脱敏**：`field_level_security.py` 单元格 redaction |
| **操作审批流** | 交互式 confirm | 交互式 confirm + deny/ask/allow 规则 | **可编程 HITL 审批**：PolicyGate + ApprovalGate |
| **审计日志** | 无 | 无 | **完整 syscall 事件表**：谁/何时/做什么/结果 |
| **权限体系** | 无 | Managed>User>Local 三层规则 | PolicyGate **统一策略引擎** + RBAC→Marking→ObjPerm 三层现算 |
| **对象级权限** | 无 | 无 | `object_permission.py`：per-object RBAC |
| **数据留存** | 本地 SQLite | 本地文件 | 持久化 ExecutionStore + FTS5 全文索引 |
| **凭证管理** | env var | env var | `secrets.py` + `crypto.py` 加密管理 |

**核心差异**：aiPlat 有字段级脱敏、对象级权限、可编程审批流——这是企业安全合规的硬需求，三个 CLI 工具都没有。

---

## 扩展与集成面 (Dimensions 9-10)

### 9. 扩展性与集成 (Extensibility & Integration)

> 代码规模：aiPlat MCP 9 模块 + Skill 19 模块 + Hook 4 模块

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **MCP 支持** | `discover_mcp_tools()` → register to registry | `mcp-servers.json` + MCPSearch 动态发现 | **MCPRuntime** 注册为 `mcp.<server>.<tool>` + prod 安全默认 + EventBus/SSE 测试 |
| **Skill 系统** | prompt/能力包，偏自进化 | SKILL.md + Marketplace (7 official + community) | **SkillRegistry + 自动晶体化 + 后台策展** + skill_chain 依赖 + 3 个人设 |
| **Skill 数量** | 不确定 | 7+ official + community | 61 个注册 skills (40 used / 21 unused) |
| **Hook 系统** | `pre_tool_call`/`post_tool_call` plugin hooks | 6-phase hooks + Stop/SubagentStop | **4 个 Phase**：SESSION_START / PRE_LOOP / POST_LOOP / STOP + workspace hooks |
| **插件机制** | Plugin discovery (`discover_plugins()`) | Plugin Marketplace + PDK | **Package 管理**：submit_for_review → publish → 灰度发布 |
| **API 暴露** | 无 (仅 CLI) | 无 (仅 CLI) | **RESTful** Integration.execute() + 92+ wiki endpoints |
| **外部对接** | Gateway 多渠道 (CLI/IM/ACP) | IDE/CI integration | 通过 Integration + 适配器 |
| **Agent 扩展** | delegate_task subagent | Task subagents (depth limited) | **IAgent 接口 + 可插拔 loop** + SubagentCoordinator |

---

### 10. 开发体验 (Developer Experience)

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **上手难度** | 中等 (pip install) | **低** (Claude Desktop 开箱即用) | 高 (需理解微内核架构 + 多服务启动) |
| **调试工具** | print/日志 | 日志文件 + `/usage-credits` | **loop_state 快照/恢复** + checkpoint + 架构守卫 |
| **文档** | 代码注释 + 在线文档 | 官方文档 + DeepWiki 源码分析 | 代码级 + `docs/architecture/` 体系 |
| **社区/生态** | 开源 (GitHub + Discord) | 闭源 (Anthropic) | 内部自研 |
| **错误信息** | 一般 (两层 try/except JSON) | 友好 | **结构化**：LLMResult (truncated/finish_reason/error_type) |
| **配置方式** | YAML config + env var | settings.json (Managed/User/Local) | 环境变量 + Gate 动态配置 |

**Claude Code 领先**——开箱即用 + settings.json 三级配置 + 丰富的官方文档是 aiPlat 需要追赶的。

---

## 运营面 (Dimensions 11-12)

### 11. 成本效率 (Cost Efficiency)

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **Token 优化** | 分层缓存 (stable/context/volatile) | **激进压缩 (~98%)** | 6 级渐进压缩 + priority 排序 |
| **缓存命中率** | **高** (分层设计) | 中 (compaction 破坏缓存) | 中 (ephemeral overlay 较多) |
| **多轮对话开销** | 中等 | **低** (压缩后摘要精简) | 中等 (渐进策略保守) |
| **工具调用开销** | 低 (直调 handler) | 低 (typed class) | 中 (四层 Gate 额外开销) |
| **工具描述膨胀控制** | `check_fn` 过滤 | **MCPSearch 按需注入** | 渐进式暴露 (stub ~50 tokens/skill) |
| **存储成本** | 低 (SQLite) | 低 (文件) | 高 (全量持久化 ExecutionStore + 双图谱) |
| **模型切换** | `fallback_providers` 链 | `/model` 切换 | model_router + infra ModelManager 集中路由 |

**Claude Code 在 token 节省上领先**：98% 激进压缩 + MCPSearch 按需注入 + typed tool 零附加开销。

---

### 12. 测试与质量保障 (Testing & QA)

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **单元测试** | 开源可见 (pytest) | 不详 | **86 个测试** + `tests/constitution/` 架构测试 |
| **架构守卫** | 无 | 无 | **15 维检查矩阵** + `scripts/architecture_guard.sh` + CI 集成 |
| **端到端测试** | 无 | 有 (内部 CI) | LearningApplier 闭环 + pipeline sandbox |
| **灰度发布** | 无 | 无 | **有**：Prompt 灰度 + Skill 版本管理 |
| **回滚能力** | 无 | 无 | **有**：Prompt/配置回滚 + SkillRollback |
| **A/B 测试** | 无 | 无 | 支持：Learning patch 机制 |
| **Sandbox** | 无 | BashTool sandbox (seccomp) | **Pipeline Sandbox**：场景合成 + 10 种突变 + 批量验证 |
| **部署闸门** | 无 | 无 | `/pipeline/ship`：assess→security→sandbox→perf→notes |

**核心差异**：aiPlat 是唯一有灰度发布、回滚、架构守卫、sandbox、部署闸门的系统——这是企业级持续交付的标准实践。

---

## 平台面 (Dimensions 13-17)

### 13. Agent 类型与多 Agent 协作

> 代码规模：aiPlat 14 个 Agent 模块 + 45 个注册 Agent

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **Agent 类型** | 单体 AIAgent | Main agent + Task subagents | **8 种预定义类型**：ReAct/PlanExecute/Conversational/ToolUsing/RAG/MultiAgent/Reflection/Planning |
| **类型实现** | 无类型区分，配置驱动 | 主 agent + subagent depth 限制 | 7 个核心实现类：ReActAgent/ConversationalAgent/PlanExecuteAgent/RAGAgent/MultiAgent/MaterialsChatAgent/BaseAgent |
| **多 Agent 协作** | `delegate_task` spawn subagent | Task subagents (可并行) | **SubagentCoordinator** + AgentMessageBus (TASK_ASSIGN/RESULT/ERROR/PROGRESS_UPDATE/CANCEL) |
| **Agent 管理** | 无 (会话即 agent) | 无 (运行时实体) | **平台资源**：`/agents` 管理 API + workspace/engine 两层 + 生命周期状态机 |
| **注册数量** | N/A | N/A | **45 个 Agent** (core engine + workspace) |
| **通信方式** | delegate_task 结果返回 | 内部消息 | **AgentMessageBus**：5 种消息类型，Agent 间不直接调用对方方法 |

---

### 14. 模型 Provider 抽象

> 代码规模：aiPlat 34 个模型相关模块

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **API 模式** | 3 种：`chat_completions` / `codex_responses` / `anthropic_messages` | Claude API 专用 | **单 LLMClient → 多 provider**：OpenAI/DeepSeek/Qwen/LM Studio 统一走 `openai_compatible.py` |
| **模式检测** | 自动：provider + base URL heuristics | 无 (专用) | model_router + infra ModelManager 集中路由 |
| **Fallback** | `fallback_providers` 链 (429/5xx/401 触发) | 无 (单 provider) | model_router fallback chain |
| **Adapter 层** | anthropic_adapter 转 OpenAI 格式 | 无 (原生) | **4 种通用 Adapter**：InfraLLMAdapter / InfraEmbeddingAdapter / InfraRerankerAdapter / InfraAudioAdapter |
| **模型发现** | provider runtime resolution | 固定列表 | infra ModelManager 从 env vars 自动发现 + 本地扫描 (Ollama/LM Studio/vLLM) |
| **健康检查** | 无 | 无 | **infra ModelManager 标记不可达模型**，core 不自行维护模型列表 |
| **核心规则** | 无 | 无 | **单一真相源**：`get_default_model(purpose)` 全局唯一解析链 |

**Hermes 在模式自动检测上更灵活**（3 种 API 模式自动切换）。aiPlat 在模型管理层级上更严谨（infra 唯一目录 → core 消费 → management 展示）。

---

### 15. 知识管理 (Knowledge Management)

> 代码规模：aiPlat 21 个 wiki/knowledge 模块 + 48 个 harness/knowledge/ 下模块 (代码图谱 1282+ 行 + 能力图谱 870 行)

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **Wiki 知识库** | 无 | 无 | **30 页面 + 全文检索 + 双向链接** + 死链/孤立检测 |
| **本体系统** | 无 | 无 | **T-Box/A-Box**：774 triples + 15 Golden 回归 + 100 分健康 |
| **自动原子化** | 无 | 无 | LLM 从长文/视频提取 KnowledgeAtom + evidence 溯源 |
| **策展管线** | 无 | 无 | `POST /wiki/curate` 并行 + BATCH=5 + 4000 字符输入裁剪 |
| **代码图谱** | 无 | 无 | **1,257 文件 / 20,103 边** + 跨语言 + 框架感知路由 + FTS5 |
| **能力图谱** | 无 | 无 | **172 节点** (45 agents + 61 skills + 35 tools) + 健康评分 |
| **健康检查** | 无 | 无 | **11 项自动检查** + 前端 HealthDashboard |
| **视频入库** | 无 | 无 | `_load_elements_from_kb()` 直读 kb_elements 表 |
| **跨模态** | 无 | 无 | refersToImage / refersToTable / explains / belongsToSection |

**核心差异**：Hermes/Claude Code 只有文件级上下文 (MEMORY.md/CLAUDE.md)。aiPlat 有完整的**知识工程体系**——本体、原子化、策展、健康检查、双图谱。这是没有任何对比系统具备的能力。

---

### 16. 流水线/工作流编排 (Pipeline & Workflow)

> 代码规模：aiPlat 8 个 pipeline 模块

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **工作流定义** | 无 (自由对话) | 无 (自由对话) | **PipelineStageConfig**：stage 序列 + HITL + retry + artifact 交接 |
| **阶段编排** | 无 | 顺序工具调用 | PipelineEngine + routing_rules + 条件路由 |
| **HITL 审批** | 交互式 confirm | 交互式 confirm | **可编程 HITL**：config 字段驱动，暂停→人工审批→继续 |
| **产物交接** | 无 | 无 | **5 项交接协议**：做了什么/产出物在哪/如何验证/已知问题/下一步 |
| **Sandbox** | 无 | BashTool sandbox | **Pipeline Sandbox**：场景合成 + 10 种突变 + 批量验证 |
| **部署闸门** | 无 | 无 | `/pipeline/ship`：assess→security→sandbox→perf→notes |
| **失败归因** | 无 | 无 | **三维归因**：verifier / causal / mechanism + tbox_hash 回放 |

**核心差异**：Hermes/Claude Code 是自由对话模式，没有形式化的工作流。aiPlat 的 Pipeline 是企业级的——阶段编排、产物交接、HITL、sandbox、部署闸门。

---

### 17. 状态恢复与容错 (State Recovery & Fault Tolerance)

> 代码规模：aiPlat 3 个 checkpoint/snapshot 相关模块

| 对比项 | Hermes | Claude Code | aiPlat |
|--------|--------|-------------|--------|
| **暂停/恢复** | 无 | 无 | **PAUSE/RESUME**：`loop_state_snapshot` → `_resume_loop_state` 完整恢复 |
| **Checkpoint** | 无 | 无 | `_snapshot()` → `state["_checkpoints"]` + 磁盘文件 |
| **Crash 恢复** | session DB 恢复 (SQLite) | session resume | ExecutionStore 持久化 + checkpoint 回放 |
| **重试策略** | fallback model 切换 | 无 | **指数退避** + failure_strategy (fail_pipeline/skip_stage/use_fallback) |
| **降级** | 压缩 + fallback | compaction | 退化策略：`max_consecutive_llm_failures` + failure_strategy |
| **版本回放** | session lineage ID | 无 | **tbox_hash 版本化**：每次回放带 ontology 版本 |

**核心差异**：Hermes/Claude Code crash 了只能重新开始或从 session DB 恢复对话。aiPlat 支持在任意 PAUSE 点完整恢复执行状态，checkpoint 持久化，这是生产级容错要求。

---

## 17 维度汇总对照表

| # | 维度 | aiPlat | Hermes | Claude Code | OpenClaw |
|:--:|------|:------:|:------:|:-----------:|:--------:|
| 1 | 执行核心 | ✅ 微内核 ABI | ⚖️ 单体 VM | ⚖️ Tool Engine | ⚖️ Gateway OS |
| 2 | 工具系统 | ✅ 四层 Gate | ⚖️ 直调 dispatch | ⚖️ PermissionClassifier | ⚖️ Policy filter |
| 3 | 上下文压缩 | ✅ 6 级渐进 | ⚖️ 50%/85% 两段 | ✅ 98% 激进 | ⚖️ Compaction+repair |
| 4 | 提示词工程 | ✅ 灰度/回滚/审计 | ⚖️ 层分离 | ⚖️ 工具+会话 | ⚖️ Prompt modes |
| 5 | 记忆系统 | ✅ 四层+晶体化 | ⚖️ 文件+SQLite | ❌ 仅 CLAUDE.md | ❌ 无 |
| 6 | 部署运维 | ✅ 微服务可扩展 | ❌ 单进程 CLI | ❌ 单进程 CLI | ⚖️ Gateway |
| 7 | 可观测性 | ✅ TraceGate+诊断 | ❌ 基础日志 | ❌ 基础 OTEL | ❌ 无 |
| 8 | 安全合规 | ✅ 字段脱敏+对象权限 | ❌ 危险命令检测 | ⚖️ 三级规则 | ⚖️ Tool policy |
| 9 | 扩展集成 | ✅ 61 skills + 35 tools | ⚖️ MCP+plugin | ⚖️ MCP+Marketplace | ⚖️ Tool sourcing |
| 10 | 开发体验 | ❌ 上手门槛高 | ⚖️ | ✅ 开箱即用 | ⚖️ |
| 11 | 成本效率 | ⚖️ 渐进保守 | ⚖️ 分层缓存 | ✅ 98%激进+按需注入 | ⚖️ |
| 12 | 测试 QA | ✅ 灰度/回滚/Sandbox | ❌ | ❌ | ❌ |
| 13 | Agent 类型 | ✅ 8种+45注册 | ❌ 单体 | ⚖️ Main+subagent | ⚖️ Session runner |
| 14 | 模型 Provider | ✅ 4种Adapter+infra | ⚖️ 3种API模式 | ❌ 单提供者 | ❌ 单提供者 |
| 15 | 知识管理 | ✅ 本体+双图谱 | ❌ 无 | ❌ 无 | ❌ 无 |
| 16 | 流水线编排 | ✅ HITL+Sandbox+闸门 | ❌ 无 | ❌ 无 | ❌ 无 |
| 17 | 状态恢复 | ✅ Checkpoint+PAUSE | ❌ 仅session恢复 | ❌ 仅session恢复 | ❌ 无 |

**图例**：✅ = 具备/领先 · ⚖️ = 持平 · ❌ = 不具备

**计分**：✅=2分 · ⚖️=1分 · ❌=0分

| 系统 | ✅ | ⚖️ | ❌ | **总分** |
|------|:--:|:--:|:--:|:--:|
| **aiPlat** | 14 | 2 | 1 | **30** |
| Claude Code | 2 | 9 | 6 | 13 |
| Hermes | 0 | 10 | 7 | 10 |
| OpenClaw | 0 | 10 | 7 | 10 |

---

## 综合判断

### aiPlat 的不可替代壁垒 (12 个独有维度)

1. **微内核 ABI**：syscall 表 + 4 层 Gate + contextvars 内核态
2. **四层 Gate 工具系统**：不可绕过的统一安全面
3. **6 级渐进压缩**：最细粒度的 priority 排序策略
4. **Prompt 灰度/回滚**：提示词是平台可运营资产
5. **四层记忆 + 晶体化**：Hermes 启发但工程实现远超
6. **微服务可扩展**：唯一的生产级部署架构
7. **全链路可观测性**：TraceGate + 结构化事件 + 诊断面板
8. **字段级安全**：脱敏 + 对象权限 + 可编程审批
9. **灰度/A/B/回滚/Sandbox**：完整的企业级交付闭环
10. **8 种 Agent 类型 + 45 注册实例**：最丰富的 Agent 生态
11. **本体 + 双图谱**：唯一具备结构化知识工程的系统
12. **Pipeline + HITL + 闸门**：唯一具备形式化工作流编排的系统

### aiPlat 需要吸收的 (3 个维度)

| 吸收点 | 来源 | 具体做法 |
|--------|------|---------|
| **开箱即用体验** | Claude Code | 降低多服务启动复杂度，参考 Claude Desktop 的一键体验 |
| **激进压缩策略** | Claude Code | 提升压缩阈值到 ~95%，减少 token 浪费 |
| **Transcript repair** | OpenClaw | 防止 tool result 异常破坏上下文 + UUID/文件名保真 |
| **Prompt cache 分层** | Hermes | stable/ephemeral 明确分层以最大化 provider cache 命中 |

---

## 数据来源与验证

| 数据 | 来源 | 验证方式 |
|------|------|---------|
| aiPlat 代码规模 | `code_graph.db` (1,257 files / 20,103 edges) | `build_graph()` Python API 实时导出 |
| aiPlat 能力规模 | `cap_graph.db` (172 nodes / 140 edges) | `GET /api/core/capability-graph` REST API |
| aiPlat 模块分布 | 代码图谱按文件路径正则分类 | 13 个维度的正则聚合 |
| Hermes 架构 | hermes-agent.nousresearch.com 开发者文档 | 3 篇代码级专题 (Agent Loop / Prompt Assembly / Tools Runtime) |
| Claude Code 架构 | deepwiki.com/anthropics/claude-code | 2 篇源码分析 (Tool System / Context Compaction) |
| OpenClaw 架构 | deepwiki.com/openclaw/openclaw | 4 篇源码分析 (Tools / Policy / Prompt / Compaction) |

> 本文档基于 2026-06-16 的代码图谱和能力图谱实时导出数据生成。可通过 `curl http://localhost:8002/api/core/diagnostics/code-intel/export` 重新导出验证。
