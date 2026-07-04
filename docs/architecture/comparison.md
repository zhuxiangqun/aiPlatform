# aiPlat 架构对标 — 四方案深度对比

> 最后更新: 2026-07-04 | Phase 5 竞品借鉴已全部合入 | 数据源: 代码级分析
> 对标对象: [Hermes Agent](https://github.com/NousResearch/hermes-agent) · [Claude Code](https://github.com/anthropics/claude-code) · [OpenClaw](https://github.com/openclaw/openclaw)
>
> **规则**: 本文档是 aiPlat 与其他系统的架构对比统一入口。新增对标方只需加一个章节。

---

## 一、四方案核心定位

| | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|------|------|------|------|------|
| **定位** | 企业 FDE 操作系统 | 个人 AI 助手 | 编程 Agent | 个人 AI 助手 |
| **语言** | Python (FastAPI) | Python (~82%) | 闭源引擎 + TS SDK | TypeScript (Node.js) |
| **架构风格** | 4 层分层 (infra/core/platform/app) | 单体 AIAgent 类 | 闭源引擎 + 开源插件层 | 单 Gateway 守护进程 |
| **开源** | 全栈开源 | MIT 开源 (核心) | 引擎闭源/插件开源 | MIT 开源 |
| **多租户** | ✅ 原生支持 | ❌ 单用户 | ❌ 单用户 | ❌ 单用户 |
| **能力数** | 398✅ | — | — | — |
| **Stars** | — | 207k | 135k | 381k |

> **注**: Hermes Agent 核心框架 (AIAgent 类、工具系统、提示词组装) 为 MIT 开源；Enterprise Gateway 和高级 OAuth 需商业授权。

---

## 二、架构图对照

```
aiPlat (4层分层)                    Hermes Agent (单体+插件)
┌────────────────────────┐          ┌─────────────────────────┐
│ L3: App/Management     │          │ Entry Points (CLI/       │
│     UI + Dashboard     │          │ Gateway/ACP/API Server)  │
├────────────────────────┤          ├─────────────────────────┤
│ L2: Platform (网关)     │          │ AIAgent Core            │
│     路由/鉴权/限流      │          │ ┌─────────────────┐    │
├────────────────────────┤          │ │Prompt Builder    │    │
│ L1: Core (AI引擎)       │          │ │Provider Resolver │    │
│ ┌──────────────────┐   │          │ │Tool Dispatch     │    │
│ │Harness (OS内核)   │   │          │ └─────────────────┘    │
│ │Agents/Skills/Tools│   │          ├─────────────────────────┤
│ │Memory/Knowledge/  │   │          │ Plugins: Memory/        │
│ │Learning/Ontology  │   │          │ Context Engine/Skills/  │
│ └──────────────────┘   │          │ MCP/Channels            │
├────────────────────────┤          └─────────────────────────┘
│ L0: Infra (模型/DB/网络)│
└────────────────────────┘

Claude Code (闭源引擎+开源插件层)        OpenClaw (Gateway)
┌────────────────────────┐          ┌─────────────────────────┐
│ UI Layer (Term/VS Code/ │          │ 22+ Messaging Channels  │
│  Web/Desktop/Slack)     │          ├─────────────────────────┤
├────────────────────────┤          │ Gateway (WebSocket,      │
│ Agentic Engine (闭源)   │          │ 127.0.0.1:18789)        │
│ ┌──────────────────┐   │          │ ┌─────────────────┐    │
│ │Agentic Loop      │   │          │ │Agent Runtime    │    │
│ │Tools/Skills/Hooks│   │          │ │Sessions/Tools/  │    │
│ │Subagent/Compact  │   │          │ │Memory/Skills    │    │
│ └──────────────────┘   │          │ └─────────────────┘    │
├────────────────────────┤          ├─────────────────────────┤
│ Extensions (MCP/        │          │ Canvas + A2UI +         │
│  Plugins/Skills/Hooks)  │          │ Companion Apps          │
└────────────────────────┘          │ (macOS/iOS/Android)     │
                                     └─────────────────────────┘
```

---

## 三、9 维度核心能力深度对照

### 维度 1: Harness 执行引擎

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|------|------|------|------|------|
| **执行模式** | ReActLoop + PipelineEngine 多阶段调度 | 同步对话循环 (`run_conversation()`) | Agentic Loop (Gather→Act→Verify) | 嵌入式 Agent Runtime (单进程) |
| **循环控制** | 14 Hook 阶段 + Token 预算 (100K) + FailureClassifier | 90 迭代上限 + Grace Call + 可中断 | Subagent 隔离 + 自动纠偏 | 每 session 串行队列 + 超时 48h |
| **声明式图编排** | ✅ LangGraph (YAML 驱动 + checkpoint + 条件边 + 可视化) | ❌ 无 | ❌ 无 (但有 Subagent 并行 + Fork 模式) | ❌ 无 |
| **多模式** | 5 routing_modes (static/llm/debate/swarm/roundtable) | Agent 间通过 `delegate_task` + 独立上下文 | Subagent + Fork + Agent Teams | 多 Agent 路由 (deterministic binding) |
| **回退/恢复** | Checkpoint + Snapshot + HITL 暂停/恢复 | 中断事件 + Ctrl+C 不损坏状态 | Checkpoint (独立于 Git) + Esc 回退 | JSONL 转录 + 会话锁定 |
| **并行执行** | ParallelExecutor + Map-Reduce + Semaphore | ThreadPoolExecutor 多工具并发 | PostToolBatch 并行工具调用 | 串行（单一队列） |
| **失败处理** | FailureClassifier + 降级策略 (fail_pipeline/skip_stage/use_fallback) | Fallback Provider 链 (18+) + 凭证刷新 | 自动重试 | 超时 + Stalled Session 检测 |

### 维度 2: 记忆子系统

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|------|------|------|------|------|
| **架构层次** | ✅ 4 层 (Working/Episodic/Semantic/TaskSkills) | 2 层 (会话内 + MEMORY.md) + 可插拔 MemoryProvider | 2 层 (会话 + Auto Memory) + Agent Memory | 文件层 + 可插拔 MemoryBackend (SQLite/QMD/Honcho) |
| **Working 记忆** | deque 滑动窗口, 30K token 限制 | 会话内保留 | 会话内保留 | 会话内保留 |
| **Episodic 记忆** | 规则摘要 + LLM 预评分 (>0.8 永不压缩) | MEMORY.md 持久化 | Auto Memory (Claude 自动学习保存) | MEMORY.md + memory/*.md (Markdown 文件) |
| **Semantic 记忆** | SQLite + FTS5 + ✅ Markdown 双写 (人类可验证) | FTS5 Session Search | 无独立实现 | 语义混合搜索 (vector + keyword) |
| **Task Skills** | Pipeline 完成自动晶体化 (pass_rate ≥85%) + 注册 SkillRegistry | Agent 自创技能 + 修补过时技能 | 无可复用 Skill 机制 | 无可复用机制 |
| **压缩策略** | ✅ 5 级 ContextCompression (70%→99%) + 工具输出预算帽 | 2 级压缩 (Preflight >50% + Gateway >85%) | Auto Compaction + Manual `/compact` | Auto Compaction + 静默 Memory Flush |
| **投毒防御** | ✅ source_tag + trust_weight + provenance 三字段 + 写前校验 | ❌ 无 | ❌ 无 | ❌ 无 |
| **记忆进化** | AutoLearner + SkillEvolver + 自动晶体化 + 语义续期 | Agent 自创技能 + MEMORY.md 自管理 | Auto Memory (自动学习保存项目知识) | Dreaming (记忆整合) + Grounded Backfill |

### 维度 3: Agent 系统

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|------|------|------|------|------|
| **Agent 类型** | 7 种实现类 (ReAct/Conv/PlanExe/RAG/MultiAgent/MaterialsChat/Base) | 单一 AIAgent 类，配置差异 | 内建 Subagent 类型 (Explore/Plan/General-purpose) | 多 Agent 配置 (`agents.list[]`) |
| **注册机制** | AGENT.md frontmatter → PipelineStageConfig + agent_registry | 无注册表，单实例运行 | 无需注册，直接创建 | 配置文件声明 |
| **Subagent** | SubAgentCoordinator + ✅ isolate_context + read_only_context | delegate_task → 独立上下文 + 预算 | ✅ 完全上下文隔离 + 仅返回摘要 | sessions_spawn (轻量) |
| **Agent 通信** | AgentMessageBus (TASK_ASSIGN/RESULT/ERROR/CANCEL) | 子代理返回最终文本 | 父子通过摘要通信 | 直接消息发送 |
| **动态路由** | DynamicRouter (LLM Supervisor) + GoalAwareRouter | 无 | 无 | Deterministic binding (规则驱动) |
| **辩论模式** | ✅ debate.py (N-Agent 对抗 + Manager 合成) | ❌ 无 | ❌ 无 | ❌ 无 |
| **竞选择优** | ✅ swarm.py (同任务分发→Arena 评分→胜出合并) | ❌ 无 | ❌ 无 | ❌ 无 |
| **圆桌讨论** | ✅ roundtable.py (平等协作 + 共识收敛) | ❌ 无 | ❌ 无 | ❌ 无 |

### 维度 4: Skill 系统

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|------|------|------|------|------|
| **技能数量** | 31 Engine + ~45 Workspace | ~18 类别内置 + Optional | 用户自建 `.claude/skills/` | 用户自建 + ClawHub |
| **执行方式** | `execution_type: handler/prompt/python_class` | SKILL.md 指令注入 + skill_manage tool | SKILL.md 指令注入 (user-invoke + model-auto) | SKILL.md 指令注入 (XML 格式) |
| **注册机制** | SkillRegistry + YAML frontmatter | 技能目录自动加载 | 文件系统扫描 + description 匹配 | 文件系统扫描 |
| **自我进化** | ✅ AutoLearner + SkillEvolver + SkillSimulator (Docker 沙盒预检, pass≥80%) | ✅ Agent 自创技能 + 修补过时技能 | ❌ 无 | ❌ 无 |
| **技能市场** | ❌ 无 | agentskills.io 兼容 | ❌ 无 | ClawHub (clawhub.ai) |
| **Lint/验证** | Skill Lint 10 规则 + Schema 校验 | ❌ 无 | ❌ 无 | ❌ 无 |
| **副作用声明** | ✅ `effects` YAML (read/write/execute, idempotent, rollback) | ❌ 无 | ❌ 无 | ❌ 无 |
| **版本/回滚** | 语义化版本 + 回滚闭环 | ❌ 无 | ❌ 无 | ❌ 无 |

### 维度 5: MCP 协议

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|------|------|------|------|------|
| **MCP 客户端** | ✅ MCPClient + MCPClientManager + Runtime | ✅ Both stdio/HTTP + OAuth 2.1 + mTLS | ✅ Full MCP 集成 | 通过插件 |
| **MCP 服务端** | ✅ MCPServer + create_mcp_server | ✅ `hermes mcp serve` (10 tools) | ✅ `claude mcp serve` | 通过插件 |
| **工具延迟加载** | ✅ Lazy Load (启动仅加载名称, Schema按需获取, AIPLAT_MCP_LAZY_LOAD) | ❌ 全量加载 | ✅ **默认仅加载名称** (~120 tokens) | ❌ 全量加载 |
| **动态工具更新** | ❌ 无 | ✅ `list_changed` 通知 | ✅ `list_changed` 通知 | ❌ 无 |
| **OAuth 支持** | ❌ 无 | ✅ PKCE + Token Exchange + mTLS | ✅ OAuth 2.0 内置流程 | 通过插件 |
| **安全分层** | PolicyGate 统一门禁 | ❌ 无 | Permissions 引擎强制执行 | Tool Policy 前置过滤 |

### 维度 6: Tool 系统

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|------|------|------|------|------|
| **工具数量** | ~19 内置 + MCP | 70+ 内置 + MCP | ~20+ 内置 + MCP | ~15+ 内置 + MCP |
| **注册机制** | ToolRegistry + BaseTool 子类 | 导入时 `registry.register()` 自发现 | 内置自动注册 | `api.registerTool()` |
| **权限系统** | PolicyGate + ApprovalGate + ✅ **3层(deny>ask>allow)** + RBAC | 危险命令检测 + 写审批 + 路径安全 | ✅ **3 层优先级 (deny>ask>allow)** + 6 种模式 + 参数级匹配 | Allow/Deny 列表 + Exec 批准 |
| **沙箱** | PipelineSandbox | ❌ 无内置（依赖 OS） | ✅ **OS 级文件系统+网络隔离** | Docker/SSH/OpenShell |
| **Browser** | BrowserTool (10 actions) | 10 browser tools (cdp/camofox/supervisor) | ❌ 无内置 | puppeteer-based |
| **后台执行** | Cron + Async Task | Cron + Background 子代理 | Background Tasks + Monitor | Cron + Heartbeat |

### 维度 7: 提示词工程

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|------|------|------|------|------|
| **模板管理** | ✅ `prompt_loader._register()` + `_sync_resolve()` (55+ 模板, 分类管理) | ❌ 硬编码在代码中 | ❌ CLAUDE.md 用户自写 | ❌ SKILL.md 指令注入 |
| **CoT 自动注入** | ✅ 引擎层自动追加 4 步推理指令 (`cot-auto-inject` 模板) | ❌ 无 | ❌ 模型自行推理 | ❌ 无 |
| **提示词缓存** | ✅ cache_control注入 + stable/volatile分离 (AIPLAT_PROMPT_CACHE) | ✅ **Anthropic Prompt Caching (字节稳定, SQLite 跨会话恢复)** | ✅ **3 层缓存 (系统+项目+会话)** | ❌ 无 |
| **动态组装** | PromptAssembler (stable_system_prompt vs ephemeral_overlay) | 3 层组装 (Stable→Context→Volatile) | CLAUDE.md 注入 (用户消息, 非系统提示) | System Prompt + Skills XML 注入 |
| **安全规则** | ✅ 注入检测 (6 正则) + PII 脱敏 + 特殊 Token 过滤 + override guard | Threat Patterns 扫描 + 作用域检测 | 引擎强制 deny 规则 (模型不可绕过) | ❌ 无内置 |
| **模型适配** | Model Injection (单一适配器, 按 capability 类型) | 18+ Provider + 3 API 模式 + Fallback 链 | 专有 Anthropic API | Provider 配置 |

### 维度 8: 知识管理

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|------|------|------|------|------|
| **知识存储** | WikiEngine (MD + FTS5) + GraphIndex + SQLite | MEMORY.md + USER.md (Markdown 文件) | CLAUDE.md + Auto Memory (MEMORY.md) | MEMORY.md + memory/*.md (Markdown 文件) |
| **检索系统** | Ontology-first → FTS5 → HyDE (CRAG 3 级回退 + RRF 融合) | FTS5 Session Search + Web Search | 文件搜索 (Glob/Grep) + MCP | 语义混合搜索 (vector + keyword) |
| **本体引擎** | ✅ **13 步 OntologyEngine** (Classify→Extract→Graph→Inference→Traverse, Palantir 对齐) | ❌ 无 | ❌ 无 | ❌ 无 |
| **域路由** | ✅ 3 级 DomainRouter (关键词 <1ms + Embedding ~50ms + LLM ~300ms) | ❌ 无 | ❌ 无 | ❌ 无 |
| **知识图谱** | CodeGraph + CapabilityGraph + SkillGraph + ShardedGraphIndex | ❌ 无 | ❌ 无 | ❌ 无 |
| **语义缓存** | ✅ 3 层 SemanticCache (精确/语义 ≥0.95/穿透) | ❌ 无 | Prompt Caching (API 端) | ❌ 无 |
| **溯源** | ✅ ProvenanceTracker (声明级引用) + 源文档更新→标记过期 | ❌ 无 | ❌ 无 | ❌ 无 |

### 维度 9: 业务价值系统

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|------|:---:|:---:|:---:|:---:|
| **ValueDashboard** | ✅ CEO/CFO/PM 三视角 | ❌ | ❌ | ❌ |
| **五维价值计量** | ✅ 效率/质量/安全/创新/体验 | ❌ | ❌ | ❌ |
| **BusinessGoalTracker** | ✅ 目标设定→进度追踪→偏离预警 | ❌ | ❌ | ❌ |
| **GoalAwareRouter** | ✅ 目标感知调度 (Speed/Quality/Safety) | ❌ | ❌ | ❌ |
| **月度价值快照** | ✅ EvolutionEngine Step 12 自动计算 + 三受众翻译 | ❌ | ❌ | ❌ |
| **ROI 计算** | ✅ 企业 Agent 投资回报量化 | ❌ | ❌ | ❌ |
| **FDE Dashboard** | ✅ 4 卡聚合 (待决策/信号预警/执行异常/训练) + 时间轴 | ❌ | ❌ | ❌ |
| **Spec 生命周期** | ✅ DRAFT→STABLE 6 状态版本演进 | ❌ | ❌ | ❌ |

> **核心差异**: Hermes/Claude Code/OpenClaw 都是"工具"或"助手"——帮用户完成任务。aiPlat 是"企业操作系统"——帮企业量化 Agent 是否推动了核心战略。

---

## 四、aiPlat 的体系性优势

| # | 维度 | 独有/领先 |
|:---:|------|------|
| 1 | **FDE 操作系统** | 唯一为 FDE 角色设计的完整工具体系 (Dashboard + SpecDetail + 全域诊断) |
| 2 | **Spec 生命周期** | DRAFT→STABLE 6 状态版本演进，同类系统无此概念 |
| 3 | **三层 Loop 传动轴** | SpecLifecycle + FeedbackRadar + TraceVisualizer |
| 4 | **5 routing_modes** | static/llm/debate/swarm/roundtable 完整覆盖 |
| 5 | **全域诊断** | 14 项跨旅程自动化验证 |
| 6 | **业务价值系统** | ValueDashboard + 五维计量 + GoalAwareRouter (四系统唯一) |
| 7 | **Ontology 引擎** | 13 步认知管线 + Palantir 对齐 (四系统唯一) |
| 8 | **CoT + 自纠错** | 引擎层自动注入，所有 Agent 受益 |
| 9 | **4 层记忆** | Working→Episodic→Semantic→TaskSkills + 投毒防御 |
| 10 | **竞品借鉴闭环** | Phase 5 完成: 8/8 已合入 (MCP懒加载 + Prompt Caching + 三层权限 + Subagent隔离 + File记忆 + Plugin Slot + Auto Memory + Skill Marketplace) |
| 10 | **竞品借鉴闭环** | Phase 5 完成: 8/8 已合入 (MCP懒加载 + Prompt Caching + 三层权限 + Subagent隔离 + File记忆 + Plugin Slot + Auto Memory + Skill Marketplace) |
| 11 | **文档-代码同步** | CI 强制统计表一致性 (427✅) + code-doc-gap 检测 + 路径标准化158条 |
| 12 | **平台能力提升 (碎石路→高速公路)** | Spec→promote→approve→SkillRegistry。FDE 一线经验沉淀为全平台可复用能力 (Palantir 模式) |

---

## 五、可从其他系统借鉴

> **实施状态 (2026-07-01)**: 全部 10 项已合入，CAPABILITIES 384→464，P0-P3 安全/测试全闭环。

| 来源 | 能力 | 理由 | 优先级 | 状态 |
|------|------|------|:---:|:---:|
| Claude Code | **MCP 工具延迟加载** (仅加载名称, Schema 按需) | aiPlat 全量加载会撑爆上下文窗口 | P0 | ✅ |
| Hermes | **Prompt Caching** (Anthropic 字节稳定 + SHA256 跨会话持久化) | 可大幅降低 API 成本 | P0 | ✅ |
| Claude Code | **Permissions 3 层优先级** (deny > ask > allow, 参数级匹配) | 比当前 PolicyGate 更精细化 | P1 | ✅ |
| Claude Code | **Subagent 完全上下文隔离 + 仅返回摘要** | 当前 SubAgentCoordinator 在同一个上下文 | P1 | ✅ |
| OpenClaw | **File-based Memory (Markdown) 作为标准答案** | 透明、人类可读、可编辑 | P1 | ✅ |
| Hermes | **工具导入时自发现** (`registry.register()` at import time) | 减少手动注册维护 | P2 | ✅ |
| OpenClaw | **Plugin Slot 模式** (同一时刻单一插件活跃) | 避免上下文碎片化 | P2 | ✅ |
| Hermes/OpenClaw | **Skill Marketplace** (agentskills.io URL一键安装) | 接入外部技能生态 | P2 | ✅ |

---

*最后更新: 2026-07-01*  
*历史版本存档: `aiPlat_arch_vs_hermes.md` → `docs/archive/`*  
*历史版本存档: `架构对照-aiPlat-vs-Hermes-vs-ClaudeCode-vs-OpenClaw.md` → `docs/archive/`*  
*历史版本存档: `aiPlat-vs-hermes-vs-claude-code-vs-openclaw-architecture.md` → `docs/archive/`*
