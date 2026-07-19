# aiPlat — 四平台深度对标分析

> 生成时间：2026-07-19 | 对标范围：aiPlat △2026-07-19 × Hermes △v0.18.2 × Claude Code △latest × OpenClaw △latest
>
> 数据来源：aiPlat 内部代码（CAPABILITIES 748✅）+ 三平台开源仓库（GitHub README + 代码结构分析）

---

## 一、四平台核心定位

| 维度 | aiPlat | Hermes Agent | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **定位** | 企业 AI 操作系统（本体驱动 FDE） | 自学习个人 AI 助手 | 终端编程 Agent | 个人 AI 助手 |
| **语言** | Python | Python 82% + TS 16% | Python 80% + Shell 14% | TypeScript |
| **GitHub** | 私有仓库 | 217k⭐ · 40.8k fork · 16,243 commits | 138k⭐ · 22.2k fork · 705 commits | 383k⭐ · 80.5k fork · 70,598 commits |
| **协议** | 私有 | MIT | 闭源引擎 + 开源插件 | MIT |
| **版本** | v2.8 (748✅) | v0.18.2 (2026.7.7) | latest | latest |
| **架构层级** | 8 层（本体语义→知识创造→上下文注入→质量评分→FDE诊断→治理→自演进→编码宪法） | 单体 Agent 结构 | 插件化 Agent（`.claude-plugin/`） | Gateway + Agent + Nodes 三层 |
| **行业定位** | 企业 FDE 交付 + 行业解决方案 | 个人消费者 + 开发者工具 | 专业开发者编程辅助 | 个人消费者 + 社区驱动 |

---

## 二、12 维度关键技术对标

### 维度 1：Harness 执行内核

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **执行循环** | ReAct + Plan-Execute + LangGraph 三模式 | ReAct 循环（推理→行动→观察） | 闭源 Agent 引擎 | Agent 循环 |
| **Hook 系统** | 6 阶段 Hook（PreLoop/PostLoop/PreReasoning/PostReasoning/PreAct/PostObserve） | 事件驱动 Hook | 无公开 Hook | 工具级拦截 |
| **Token 预算** | 5 级压缩（70/80/85/90/99%）+ 温度感知剪枝 + 语义排序 | 上下文压缩（`/compress`） | 自动压缩 | 自动管理 |
| **多终端后端** | 单进程 server | Docker/SSH/Singularity/Modal/Daytona | CLI only | Docker + 本地 |
| **Subagent** | SubagentCoordinator + AgentMessageBus | ✅ 并行工作流 + RPC 零上下文 | ✅ 原生 subagent | ✅ sandbox 隔离 |

**aiPlat 领先项**：Hook 系统粒度 × Token 预算 × LangGraph 集成 × 5 级压缩体系

**aiPlat 可借鉴**：Hermes RPC 零上下文 Subagent 模式（aiPlat subagent 需加载完整上下文）

---

### 维度 2：Agent 系统

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **Agent 类型** | ReAct / Plan-Execute / Conversational / RAG / Multi-Agent / Reflection | ReAct 为主 | 闭源 Agent 引擎 | 可配置 Agent 模式 |
| **多 Agent** | SubagentCoordinator + 消息总线 | Subagent 并行工作流 | 原生 subagent | Multi-agent routing + sandbox |
| **Agent 注册** | AGENT.md frontmatter + Registry 自动发现 | AGENTS.md + skills 目录 | CLAUDE.md | AGENTS.md + SOUL.md + TOOLS.md |
| **身份注入** | tenant/actor/roles 三层头注入 | 用户配置 | OAuth | 用户配置 |
| **消息通道** | ReActLoop REST API | Telegram/Discord/Slack/WhatsApp/Signal/CLI | CLI only | 23 通道（含 WeChat/QQ） |
| **自学习** | ✅ SECI 引擎（S→E→C→I→S 螺旋） | ✅ 闭环学习：自主技能创建→使用中改进 | ❌ | ❌ |

**aiPlat 领先项**：Agent 类型多样性 × 自学习 SECI 引擎 × 三层身份注入

**aiPlat 可借鉴**：OpenClaw 23 通道模型（考虑扩展 FDE 的消息通道）

---

### 维度 3：Skill 系统

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **Skill 定义** | SKILL.md frontmatter + handler.py（Python 类）/ prompt（LLM） | agentskills.io 开放标准 | Custom Commands（`.claude/commands/`） | ClawHub（`skills/<name>/SKILL.md`） |
| **数量** | 44 engine + 21 workspace | 社区 + optional-skills 目录 | ~10 built-in | 社区 + workspace |
| **执行方式** | handler（确定性）+ prompt（LLM 模拟）| prompt + handler | Command 形式 | SKILL.md 形式 |
| **跨平台标准** | 自定义（YAML frontmatter） | ✅ agentskills.io（开放标准） | 自定义 | 自定义 |
| **自主创建** | ✅ ActiveSynthesis + STORM 5步 | ✅ 复杂任务后自动创建技能 | ❌ | ❌ |
| **审计** | ✅ AIPLAT_EXECUTION_AUDIT=true | ❌ | ❌ | ❌ |

**aiPlat 领先项**：执行类型双模式 × 自主创建 × 执行审计

**aiPlat 可借鉴**：Hermes agentskills.io 开放标准（考虑兼容）

---

### 维度 4：MCP 集成

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **MCP 管理** | 统一归属 core/apps/mcp/ + PolicyGate | optional-mcps/ 目录 | MCP Registry 集成 | MCP 工具注册 |
| **工具适配** | MCPToolAdapter（extends BaseTool） | 内置 MCP 客户端 | 内置 MCP 客户端 | 内置 MCP 客户端 |
| **安全** | PolicyGate + ApprovalGate 双重门禁 | DM 配对机制 | 命令审批 | DM 配对 + sandbox |

**aiPlat 领先项**：统一归属 + 双重门禁

---

### 维度 5：记忆系统

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **分层** | 4 层（Working / Episodic / Semantic / Task Skills） | Honcho 对话建模 + FTS5 搜索 | CLAUDE.md 永驻上下文 | SOUL.md + TOOLS.md |
| **搜索** | FTS5 + 嵌入语义 + 跨会话 | FTS5 全文搜索 + LLM 摘要 | 项目级上下文 | 项目级上下文 |
| **长期记忆** | SQLite long_term_memories + 自动过期 | MEMORY.md + USER.md | 会话内 | 会话内 |
| **压缩** | 5 级（70/80/85/90/99%）+ 温度感知 + 语义排序 | 手动 /compress | 自动压缩 | 自动管理 |
| **跨会话** | ✅ 语义记忆续期 + 跨会话召回 | ✅ FTS5 + LLM 摘要 | ⚠️ 单会话 | ⚠️ 单会话 |

**aiPlat 领先项**：4 层架构 × 5 级压缩 × 语义排序 × 跨会话持久化

---

### 维度 6：知识库管理

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **本体驱动** | ✅ YAML 域本体 + GraphIndex + 13步引擎 | ❌ | ❌ | ❌ |
| **向量存储** | ✅ InfraEmbeddingAdapter + FTS5 | 项目文件 | 项目文件 | 项目文件 |
| **知识合成** | ✅ KnowledgeSynthesizer（3 类型） | ❌ | ❌ | ❌ |
| **外部本体导入** | ✅ OWL/SKOS/JSON-LD | ❌ | ❌ | ❌ |
| **域路由** | ✅ DomainRouter 3 层级联 | N/A | N/A | N/A |

**aiPlat 领先项**：本体驱动 × 13步引擎 × 知识合成 × 外部导入 × 域路由

**核心差异**：aiPlat 是本系列中唯一拥有结构化知识引擎的平台。

---

### 维度 7：RAG 检索增强

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **检索模式** | CRAG 3 级回退 + HyDE + Self-RAG | FTS5 全文搜索 + LLM 摘要 | Codebase 搜索 | 工具搜索 |
| **检索融合** | RRF 融合（Wiki + KB + Graph） | 无融合 | 无融合 | 无融合 |
| **质量门** | CRAG（本体优先→FTS5→HyDE）| 无 | 无 | 无 |

**aiPlat 领先项**：CRAG 多级回退 × RRF 融合 × 本体优先路由

---

### 维度 8：提示词工程

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **模板管理** | prompt_loader（`_register()` + `_sync_resolve()`）+ 版本化 | AGENTS.md + skills | CLAUDE.md | AGENTS.md + SOUL.md |
| **注入机制** | 10 层 ContextBus + CLAUDE.md 永驻 | 直接注入 | 直接注入 | 直接注入 |
| **编码宪法** | ✅ karpathy_v1 全局默认 | ❌ | ❌ | ❌ |
| **模板数量** | 65+ 模板 | 无集中管理 | 无集中管理 | 无集中管理 |

**aiPlat 领先项**：模板集中管理 × 编码宪法 × 10 层注入

---

### 维度 9：可观测性

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **追踪** | trace_id/span_id 全链路 | 基本日志 | 基本日志 | 基本日志 |
| **审计** | ✅ usage_tracker + AIPLAT_EXECUTION_AUDIT | ❌ | ❌ | ❌ |
| **OpenTelemetry** | ✅ OTLP（AIPLAT_OTEL_ENABLED） | ❌ | ❌ | ❌ |
| **诊断矩阵** | 37 类检查 + 架构守卫 | ❌ | ❌ | ❌ |

**aiPlat 领先项**：全链路追踪 × 执行审计 × OTEL × 诊断矩阵

---

### 维度 10：幻觉检测与事实核查

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **幻觉检测** | ✅ HallucinationTracker（NLI + Faithfulness） | ❌ | ❌ | ❌ |
| **事实核查** | GraphInference + RRF + Self-RAG | ❌ | ❌ | ❌ |
| **语义缓存** | ✅ L1+L2+L3 语义缓存 | ❌ | ❌ | ❌ |

**aiPlat 领先项**：幻觉检测 × 语义缓存 × 事实核查三层防护

---

### 维度 11：自演进系统

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **自演进引擎** | ✅ SECI 引擎（S→E→C→I→S）+ EvolutionEngine | ❌ | ❌ | ❌ |
| **诊断→修复→演化** | ✅ SystemDiagnostician → Healer → Evolver | ❌ | ❌ | ❌ |
| **反馈闭环** | ✅ FeedbackLoops + CandidatePool + ActiveSynthesis | ✅ 自学习闭环（技能创建→使用中改进） | ❌ | ❌ |
| **Cron 自动化** | ✅ governance cron + learning scheduler | ✅ 自然语言 cron 任务 | ❌ | ✅ cron jobs |

**aiPlat 领先项**：完整的诊断→修复→演化闭环 × SECI 引擎 × 反馈闭环

**Hermes 领先项**：自主技能创建的学习闭环（aiPlat 有 ActiveSynthesis 对标，但执行路径不同）

---

### 维度 12：治理体系（v2.8 新增）

| 能力 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---|:---|:---|:---|
| **本体变更审批** | ✅ OntologyApproval（submit/approve/reject） | ❌ | ❌ | ❌ |
| **治理管线** | ✅ GovernancePipeline（6步循环） | ❌ | ❌ | ❌ |
| **映射验证** | ✅ MappingValidator（类型/枚举/覆盖率） | ❌ | ❌ | ❌ |
| **治理仪表盘** | ✅ 健康总分 + 7 机制状态 + 审批队列 | ❌ | ❌ | ❌ |
| **RBAC 治理角色** | ✅ 4 种治理角色 × 12 种权限 | ❌ | ❌ | ❌ |

**aiPlat 独有**：三平台均无正式的本体治理体系。

---

## 三、aiPlat 体系性领先优势（12 项）

| # | 能力 | 独有程度 |
|:---:|------|:---:|
| 1 | YAML 驱动本体引擎（15 域 × 40+ 模块） | 独有 |
| 2 | 13 步本体引擎管线（12 步确定性 + 1 步 LLM） | 独有 |
| 3 | GraphIndex 双向图 SQLite 存储（含超边 + 快照） | 独有 |
| 4 | DomainRouter 3 层级联（T1 标签 <1ms → T2 嵌入 50ms → T3 LLM 300ms） | 独有 |
| 5 | SECI 知识创造引擎（S→E→C→I→S 螺旋） | 独有 |
| 6 | GovernancePipeline 6 步治理闭环 | 独有 |
| 7 | OntologyAgent 5 步推理编排（理解→规划→查询→评分→输出） | 独有 |
| 8 | ScoringEngine 累加加权评分（via_path 多跳 + 阈值按成熟度自适应） | 独有 |
| 9 | PathPlanner 目标导向路径规划（预定义模板 + 自动发现 fallback） | 独有 |
| 10 | ScenarioSelector 4 象限场景优先级（5 条件评估） | 独有 |
| 11 | 4 层记忆体系（Working + Episodic + Semantic + Task Skills） | 群领先 |
| 12 | 5 级上下文压缩（温度感知 + 语义排序 + 跨层重排） | 群领先 |

---

## 四、从三平台可借鉴的能力

| 来源 | 能力 | 借鉴价值 | 对 aiPlat 的建议 |
|:---|------|:---:|------|
| **Hermes** | agentskills.io Skill 开放标准 | 高 | 考虑兼容该标准，扩大 Skill 生态 |
| **Hermes** | Subagent RPC 零上下文调用 | 高 | 避免 subagent 加载完整 context，降低 token 消耗 |
| **Hermes** | 多终端后端（Modal/Daytona serverless） | 中 | 支持 serverless 部署模式 |
| **Claude Code** | Plugin 系统（`.claude-plugin/`） | 中 | 考虑插件化扩展机制 |
| **Claude Code** | Custom Commands（`.claude/commands/`） | 中 | 已有 Skill 系统，可增加快捷命令入口 |
| **OpenClaw** | 23 通道消息网关 | 中 | FDE 可扩展多通道提醒（微信/钉钉） |
| **OpenClaw** | Sandbox 隔离（Docker/SSH/OpenShell） | 高 | 增强 subagent 隔离能力 |
| **OpenClaw** | Live Canvas（A2UI Agent 驱动画布） | 低 | 可考虑 FDE 可视化推理链展示 |

---

## 五、综合评分矩阵

| 维度 | aiPlat | Hermes | Claude Code | OpenClaw |
|:---|:---:|:---:|:---:|:---:|
| 1. Harness 执行内核 | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★☆☆ |
| 2. Agent 系统 | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★★☆ |
| 3. Skill 系统 | ★★★★★ | ★★★★★ | ★★★☆☆ | ★★★★☆ |
| 4. MCP 集成 | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★★☆ |
| 5. 记忆系统 | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★☆☆ |
| 6. 知识库管理 | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| 7. RAG 检索 | ★★★★★ | ★★★☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| 8. 提示词工程 | ★★★★★ | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ |
| 9. 可观测性 | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| 10. 幻觉检测 | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| 11. 自演进系统 | ★★★★★ | ★★★☆☆ | ★☆☆☆☆ | ★☆☆☆☆ |
| 12. 治理体系 | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ | ★☆☆☆☆ |
| **加权总分** | **98** | **68** | **55** | **52** |

---

*对标基准日期：aiPlat 2026-07-19 (v2.8) · Hermes 2026-07-08 (v0.18.2) · Claude Code 2026-07 · OpenClaw 2026-07*
*权重：维度 1,2,3,5 各 10%；维度 6,7,8,11 各 8%；维度 4,9,10,12 各 7%*
