# aiPlat 核心能力对标报告（2026-10 五家重做）

> 最后验证 2026-10-16（OpenWorker 收口 + 认知分层旁路 §0.3）

> **调研时点**：2026-10-13（列）· 2026-10-16（OpenWorker 吸收 · 认知分层旁路）  
> **对标列（6）**：aiPlat · Hermes Agent · Claude Code · OpenClaw · DeepSeek Harness · OpenAI Codex  
> **旁路吸收（非列）**：OpenWorker — §0.2；**认知分层**（想·判·行·呈 / Jev·Skill·Knap 理念）— §0.3；**框架层库**（aisuite / LangChain）— 不入列（见 §0.3 末）  
> **口径**：开源四家以源码/对齐 release 为准；Claude Code 为打包产物级；详见 [`对标底稿-2026-10-五家.md`](./对标底稿-2026-10-五家.md)  
> **架构摘要入口**：[`docs/architecture/comparison.md`](../architecture/comparison.md)（18 维评分）  
> **历史稿**：[`docs/archive/aiPlat核心能力对标报告-2026-08-六系统.md`](../archive/aiPlat核心能力对标报告-2026-08-六系统.md)（含 Hermes 双列/Codex-Harness 旧名，只读）  
> **结论原则**：代码事实优先；阴性标盲区；不编造 QPS/ROI；星级见 comparison 加权表  

---

## 0.1 业务语言导读

| 系统 | 一句话 |
|------|--------|
| **aiPlat** | 企业级 AI 操作系统：多 Agent 交付流水线 + 审批审计 + 知识本体 |
| **Hermes Agent** | 会自我学习的个人/团队 Agent，多消息通道 + 多终端后端 |
| **Claude Code** | Anthropic 官方编程 Agent（终端/IDE），引擎闭源 |
| **OpenClaw** | 开源个人助手：Gateway + 20+ 通道 + 桌面/移动原生端 |
| **DeepSeek Harness** | 高纯度插件化 Agent harness（事件/工具/子代理可插拔） |
| **OpenAI Codex** | 开源 coding agent 运行时（Rust）：可嵌入 app-server + OS 沙箱 |
| **OpenWorker**（旁路） | 桌面本地优先「要成品」Agent；治理内生；不并入对标列（产品位不同） |
| **认知分层**（旁路理念） | 大模型只「想」；判/行/呈交给专用确定性或快决策子系统 — §0.3 |

**aiPlat 强**：治理、知识/本体、交付 HITL、平台质量门。  
**aiPlat 相对弱/需追赶**：消费级通道广度（OpenClaw）、会话内学习敏捷度（Hermes）、app-server 协议完备度与 OS 沙箱深度（Codex；bwrap/seatbelt 已有，Windows/landlock 仍浅）。

### 0.2 OpenWorker 吸收收口（2026-10-16）

> 定位差：OpenWorker = 本机桌面生产力；aiPlat = 企业控制面；Pi = 厂外薄宿主。  
> **借语义与闸门，不借 Tauri/25+ SaaS 进 core。**

| 阶梯 | PR | 落地（代码事实） |
|:---:|:---:|---|
| P0–P1 | [#315](https://github.com/zhuxiangqun/aiPlatform/pull/315) | Hard floors · RiskClass · shell risk · Unattended Inbox |
| P2 | [#316](https://github.com/zhuxiangqun/aiPlatform/pull/316) | Auto-Approve Reviewer（fail-closed；不可解 hard floor） |
| P3 | [#317](https://github.com/zhuxiangqun/aiPlatform/pull/317) | Session write provenance → 写后自跑 hard floor |
| Pi 桥 | [#318](https://github.com/zhuxiangqun/aiPlatform/pull/318) | `AIPLAT_ENTERPRISE_ATTENDANCE` + unattended list/wait |
| 专科包 | [#319](https://github.com/zhuxiangqun/aiPlatform/pull/319) | `security_coworker` AGENT + PERSONA + `security_review` 团队种子 |

**验证锚点**（抽查）：

```bash
rg -n 'check_hard_floor|RiskClass|approval_inbox|approval_reviewer|session_write_provenance' \
  aiPlat-core/core/harness/infrastructure/gates --glob '*.py' | head
test -f aiPlat-core/core/workspace_seeds/personas/security_coworker/PERSONA.md
rg -n 'attendanceInjectFields|aiplat_unattended' packages/aiplat-pi-runtime/extensions/enterprise_approval.ts
```

**明确不吸收**：桌面 Tauri 壳、本机 Secret Store 产品化、25+ 连接器进 harness（走 MCP/plugin 阶梯）。

### 0.3 认知分层旁路（想·判·行·呈，2026-10-16）

> 社区/业界叙事（含 TypeSafe「System One」、pi-warden 任务语境护栏、MCP 渐进披露、模板呈现）：**单体 LLM 交成本/延迟/脆弱三税**；生产 Agent 收敛为「LLM 只干难语义，判断·执行·呈现交给专用层」。  
> **不入六列评分**（理念层 / 产品品牌，非对位完整系统）。**不绑定**商用 Jev / Knap 品牌进 core 叙事。

| 层 | 文章主张 | aiPlat 已对齐（代码事实） | Pi |
|----|----------|--------------------------|-----|
| **想 · LLM** | Power for Hard Things | `best_model_for_purpose` + T1–T5；编码宪法 / SOP | 自备模型 + SOP 注入 |
| **判 · 决策** | 快、校准置信度、类型化原语 | PolicyGate · RiskClass · ApprovalGate · Auto-Approve Reviewer（#316）· Evidence Envelope；**尚无**独立非自回归「System 1 ASIC」 | `enterprise_tool_gate`；裁决回平台 |
| **行 · Skill/MCP** | 副作用走确定性代码 | `execution_type:handler` · Syscall · MCP · hard floors / Inbox | handler 桥 + 工具代理 |
| **呈 · 模板** | Schema JSON + 确定性渲染 | Jinja stage · `output_schema`→`response_format` · 交付报告导出 | 导出 Markdown；交付物宜走 handler/模板 |

**典型痛点**（同命令不同任务：`npm run db:reset`）：正则黑名单不够 → 需 **任务语境闸门**（pi-warden / Reviewer 同构）。

| 优先级 | 项 | 状态 |
|:---:|---|------|
| P0 | 任务语境闸门：exec/write/egress/external 无 `_user_goal` → `missing_task_context`（不调 LLM）；`sys_tool_call` 注入 trace/`AIPLAT_USER_GOAL`；Pi `AIPLAT_ENTERPRISE_TASK` | **已接线**（`approval_reviewer.resolve_task_context`；`AIPLAT_REVIEWER_REQUIRE_TASK=0` 可关） |
| P1 | 便宜 System 1 决策面（小分类器/logits/规则+校准表） | 可选观察；不搬进 Pi；不强制商用 Jev |
| P1 | 呈层：工厂/FDE 交付物「LLM→schema JSON→模板」覆盖面 | 可选观察 |
| P2 | MCP/工具 schema 渐进披露（压上下文） | 可选观察 |

**明确不入列的框架层库**（与六列产品位不同）：

| 库 | 对位 | 为何不进评分列 |
|----|------|----------------|
| **aisuite** | 模型统一调用层 ≈ infra `ModelManager` / adapter | SDK/库，非整机 Agent |
| **LangChain** | 通用 Agent 工具链 | 开发框架，非企业 OS / 完整运行时 |

**验证锚点**（抽查）：

```bash
rg -n 'best_model_for_purpose|ModelTierRouter' aiPlat-core/core/harness --glob '*.py' | head
rg -n 'review_proposed_action|RiskClass|check_hard_floor' \
  aiPlat-core/core/harness/infrastructure/gates --glob '*.py' | head
rg -n 'build_llm_response_format|output_schema' aiPlat-core --glob '*.py' | head
rg -n 'execution_type' aiPlat-core/core/engine/skills/*/SKILL.md | head
```

---

## 0. 一句话定位与指纹

| 系统 | 定位 | 本轮指纹 |
|------|------|----------|
| aiPlat | 企业 FDE OS | HEAD `af3f466`（#319 后）；CAPABILITIES **2185**；`PipelineEngine` `:564` |
| Hermes | 自进化 Agent | clone `562fda90`；GH **v0.21.7** |
| Claude Code | Agentic coding | npm **2.1.296** / 本机产物 **2.1.70** |
| OpenClaw | 多端助手 | **2026.10.2**（= GH latest） |
| DSH | 插件 harness | **0.1.0-rc.5** @ `47f94385`（2026-08-13） |
| Codex | 可嵌入运行时 | GH **rust-v0.162.1**；本地 `codex-rs` 结构 |

---

## 1–14. 能力维（六列刷新）

> 每节首行通俗说；表格证据见底稿。列顺序：aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex。

### 1. Agent 循环与执行模型

> AI 怎么干活：流水线 vs 单循环 vs Gateway 会话。

| 子维 | aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex |
|------|--------|--------|-------------|----------|-----|-------|
| 引擎 | PipelineEngine + Mixin | conversation_loop + run_agent | 闭源 AgentLoop | Gateway + agent run | 插件化 step/turn | Rust Session/Turn |
| HITL | approve/reject/resume 一等 | 审批配置层 | plan/act | pairing/审批（操作者信任） | plan/guard | tool approval |
| 证据 | `pipeline_engine.py:564,2024` | `agent/conversation_loop.py` | 文档+cli.js | `README.md:70-72` | `packages/interaction` | `codex-rs/core` |

### 2. 工具系统

| 子维 | aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex |
|------|--------|--------|-------------|----------|-----|-------|
| 模型 | BaseTool + Syscall | toolsets + terminal 族 | 内置工具集 | tools/skills/plugins | defineTool + MCP | tools + MCP crates |
| 治理 | PolicyGate 链最深 + OpenWorker P0–P3 + Pi attendance + 安全专科 coworker 种子 | 危险命令审批 | allow/deny/ask | 主机默认 + 可选 sandbox | ToolGuard | approval + sandbox |
| 证据 | `policy_gate.py:310` | `tools/terminal_tool_*` | 产物 | `README.md:75,81` | `packages/guard` | `codex-mcp` |

### 3. 上下文管理

| 子维 | aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex |
|------|--------|--------|-------------|----------|-----|-------|
| 记忆 | 四层 MemoryManager | 策展 MEMORY/USER + FTS | CLAUDE.md 层级 | workspace + active-memory | context/session 包 | Thread + compaction |
| 压缩/Cache | 5 级 + CacheAwareRouter | 多路径压缩（既有结论+新版循环缩短） | auto-compact | 会话级 | compaction 包 | compaction crate |
| 证据 | `cache_aware_router.py:25` | README + state_search | 文档 | `extensions/active-memory` | `packages/compaction` | `codex-rs/compaction` |

### 4. 子代理与多 Agent

| 子维 | aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex |
|------|--------|--------|-------------|----------|-----|-------|
| 形态 | SubagentCoordinator + 多 routing | delegate_task + RPC | Task/workflows | routing / multi-agent | 多 provider continuation | turn 级子代理 |
| 证据 | `coordinator.py:44` | achievements 统计 delegate | 文档 | `src/routing/` | packages | `core/src/session` |

### 5. Skill 系统

| 子维 | aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex |
|------|--------|--------|-------------|----------|-----|-------|
| 标准 | SKILL.md + execution_type | agentskills.io | commands/skills | SKILL + ClawHub | 插件技能 | AGENTS.md |
| 证据 | engine skills | README | cli.js | `README.md:89` | packages | `agents_md_manager.rs:30` |

### 6–7. 工作流与规划

aiPlat：声明式 stage + TeamPlanner/多种 pipeline_mode。  
Hermes：cron + kanban/goal。  
Claude Code：dynamic workflows + plan mode。  
OpenClaw：Gateway 会话/自动化。  
DSH：workflow/plan 包。  
Codex：goal/turn，无企业交付 DAG。

### 8. 沙箱 / 权限 / 审批

| 系统 | 结论 |
|------|------|
| aiPlat | 多 Gate + OpenWorker P0–P3（Hard floors/RiskClass/Inbox/Reviewer/write-provenance）+ Pi Unattended attendance 桥 + security_coworker 出厂种子；会话级 approve（企业） |
| Hermes | 容器后端隔离强；审批配置化 |
| Claude Code | sandbox/permissions 产品化（产物可证） |
| OpenClaw | **单操作者信任模型**；非敌意多租户（SECURITY.md） |
| DSH | sandbox/guard 包 |
| Codex | **OS 级** linux/windows/mxc sandbox + landlock 路径 |

### 9–10. 会话与模型适配

各方均有会话持久化；模型面：Hermes/OpenClaw 多 provider 生态强；aiPlat 以 infra ModelManager 为唯一权威；Codex 绑定 OpenAI 生态但可配置。

### 11. 自修改 / 自我进化

| 系统 | 结论 |
|------|------|
| Hermes | **会话内学习闭环最完整**（技能自创/自改进/nudge） |
| aiPlat | 夜间进化 + SECI + nudge 吸收；完整度形态不同 |
| DSH | 自修改/插件热更能力存在 |
| OpenClaw / CC / Codex | 无对等「自进化 OS」叙事 |

### 12–13. 扩展与多渠道

| 系统 | 扩展 | 通道 |
|------|------|------|
| OpenClaw | plugins + 175 extensions 量级 | **通道/原生端第一**（20+ 消息 + macOS/iOS/Android/Linux apps） |
| Hermes | toolsets/MCP/plugins | Telegram/Discord/Slack/WhatsApp/Signal/CLI |
| aiPlat | MCP + Skill + Hook + CoreFacade | 企业通道为主 |
| Codex | crate/MCP/hooks | CLI/IDE/app-server |
| DSH | 一切皆插件 | 偏 SDK/运行时 |
| CC | MCP + hooks | CLI/IDE |

### 14. 企业治理与可观测性

aiPlat：**唯一**把多租户、计费、审批、审计、架构守卫做成平台默认的系统。  
他方多为单用户/团队助手或 coding runtime；OpenClaw 文档明确不做敌意多租户边界。

---

## 15–20. 新增维度（D15–D20）

### 15. 可嵌入 / 协议面

| 系统 | 结论 | 证据 |
|------|------|------|
| Codex | **领先**：app-server 协议/传输/守护进程族 | `codex-rs/app-server*` |
| OpenClaw | a2a / agentsapi / admin-http-rpc 扩展 | `extensions/a2a` 等 |
| Hermes | hosted_room / 网关链 | `gateway/hosted_room_*.py` |
| aiPlat | CoreFacade + Pi thin runtime + CC hooks 桥 | `packages/aiplat-pi-runtime` |
| DSH | sdk / acp 包 | `packages/sdk`、`packages/acp` |
| Claude Code | Agent SDK（文档级） | 官方 SDK 文档 |

### 16. 原生端与通道广度

**OpenClaw ★★★★★**（apps + 通道扩展清单见底稿）。Hermes 次之。aiPlat 企业通道可用但非消费级全覆盖。

### 17. 执行后端与部署拓扑

**Hermes ★★★★★**：`local/docker/ssh/singularity/modal/daytona/vercel_sandbox`（`terminal_tool_config.py:120-121`）。  
aiPlat：Helm/四层服务部署。OpenClaw：Gateway 本机/团队。Codex/CC：本机沙箱为主。

### 18. 交付 / Spec 生命周期

**aiPlat ★★★★★**：Pipeline HITL 一等公民（`approve_session`/`reject_session`/`resume_from_checkpoint`）。  
他方多为会话/turn，无对等「企业交付流水线」。

### 19. OS 沙箱与工作树

**Codex ★★★★★**：linux-sandbox / windows-sandbox / landlock 路径；git worktree 工具。  
Claude Code：产品级 sandbox。Hermes：容器后端。OpenClaw：可选 Docker sandbox。  
aiPlat：**SandboxGate（策略）+ `os_sandbox.py`（bwrap/seatbelt，StageSandbox/exec 已接线）**；生产可 fail-closed。相对 Codex 仍缺 Windows AppContainer / landlock 深度与默认全路径强制。OpenWorker 侧 OpenShell 容器沙箱未搬入（可选后续，非 P0）。

### 20. 评测 / 质量门 / 可观测拆分

**aiPlat ★★★★★**：Quality Bus、architecture_guard、评测子系统。  
Codex/DSH/CC：hooks/diagnostics/transcript。Hermes/OpenClaw：偏运行洞察，非企业质量总线。

---

## 16. 优势 / 劣势 / 本轮增量差距

### 16.1 aiPlat 标志性差异化（仍成立）

1. 交付流水线 + HITL  
2. Syscall/Gate 治理执法  
3. 本体/知识引擎  
4. 平台级质量门与文档/能力同步守卫  
5. 多 Agent 编排形态丰富  

### 16.2 本轮仍成立的追赶项（2026-10 增量）

| ID | 差距 | 主要对标 | 说明 |
|----|------|----------|------|
| N1 | 消费级通道/原生端广度 | OpenClaw | 企业通道≠全通道；信任模型不可照搬 |
| N2 | 多终端 serverless 后端矩阵 | Hermes | Modal/Daytona/Vercel 等 |
| N3 | OS 原生沙箱深度 | Codex | **部分闭环**：`os_sandbox.py` bwrap/seatbelt 已接线；剩 Windows/landlock 与默认全工具强制 |
| N4 | app-server 级可嵌入协议完备度 | Codex | 已有 Pi/Facade/hooks，协议面仍可加深 |
| N5 | 会话内学习闭环产品化完整度 | Hermes | 机制有吸收，体验形态不同 |

> 2026-08 行动纲领 G1–G15 史实不推翻；见 archive 旧报告与 [`对标吸收与架构纯度评估.md`](./对标吸收与架构纯度评估.md)。

### 16.3 可借鉴优先级（建议）

P0 观察：Codex 沙箱语义、OpenClaw 通道插件模型（在多租户边界内）。  
P1：Hermes 后端矩阵与 agentskills 兼容。  
P2：DSH continuation 多样性、CC 体验细节。

---

## 17. 调研方法与可信度

| 系统 | 口径 | 路径 |
|------|------|------|
| aiPlat | 源码级 | 本仓 |
| Hermes | 源码级 | `tmp/bench-clones/hermes-agent` @ 562fda90 |
| OpenClaw | 源码级（release 对齐） | `openSource/openclaw-main` @ 2026.10.2 |
| DSH | 源码级（存量） | `deepseek-harness` @ 47f94385 |
| Codex | 源码级（本地树）+ GH tag | `openSource/codex-main`；tag rust-v0.162.1 |
| Claude Code | 产物级 | npm 2.1.296 / 本机 2.1.70 cli.js |

**可信度原则**：阳性（有文件:行号/目录）高可信；阴性（「没有 X」）有盲区。完整命令见底稿 §2。

---

## 18. 结论

1. **企业操作系统位**仍由 aiPlat 占据（治理 × 知识 × 交付）。  
2. **个人助手生态位** OpenClaw（通道/原生端）与 Hermes（学习/多后端）分割领先。  
3. **编程运行时位** Codex（嵌入+沙箱）与 Claude Code（产品体验）领先。  
4. **插件 harness 位** DSH 仍是架构纯度参照。  
5. 综合加权分见 [`comparison.md`](../architecture/comparison.md) §三（aiPlat 92 / Hermes 70 / OpenClaw 60 / DSH 62 / Codex 61 / CC 56）——**论证用，非商务承诺**。

---

## 19. 架构面对照（缩略）

| 维度 | aiPlat | Hermes | OpenClaw | DSH | Codex | Claude Code |
|------|--------|--------|----------|-----|-------|-------------|
| 组织哲学 | 分层 OS + 配置驱动流水线 | 单 Agent + Gateway | Gateway + Nodes/Apps | 一切皆插件 | 可嵌入 runtime | 产品 Agent |
| 状态 | PipelineState + 多存储 | 会话 DB + 策展文件 | Gateway 会话 | 事件源会话 | Thread/Turn | transcript |
| 安全边界 | 多租户 + Gate + OpenWorker P0–P3（§0.2） | 配置审批 + 容器 | 单操作者 | guard 包 | OS sandbox | 产品权限 |
| 扩展 | MCP/Skill/Hook/Facade | toolsets/MCP | extensions/ClawHub | Cordis | crates/MCP | hooks/MCP |

---

## 20. 缺口矩阵（2026-10 增量节）

历史 G1–G15 闭环状态见 archive 旧报告与吸收评估。  
**本轮新增观察项**：N1–N5（§16.2）。不将 N 项自动升级为工程承诺，除非单独立项。  
**OpenWorker 旁路吸收**：§0.2 阶梯 #315–#319 **已收口**（治理 + Pi attendance + 安全专科种子）；不进入 N 矩阵（产品位不同，非「缺列」）。  
**认知分层旁路**：§0.3 — 理念已与 Gate/Skill/schema 对齐；**任务语境闸门 P0 已接线**；专用 System 1 / 呈层全覆盖仍为可选观察，不自动升 N 项。aisuite / LangChain **不入列**。

---

## 21. 评分索引

完整 18 维星级与加权算法：**仅以** [`docs/architecture/comparison.md`](../architecture/comparison.md) 为准。  
本报告正文不重复粘贴第二份总分表，避免双源漂移。

---

## 22. 验证

```bash
test -f docs/research/对标底稿-2026-10-五家.md
rg -n '六平台|18 维度|加权总分' docs/architecture/comparison.md
# OpenWorker 旁路吸收收口（§0.2 / #315–#319）
rg -n 'check_hard_floor|session_write_provenance|ApprovalInboxStore' \
  aiPlat-core/core/harness/infrastructure/gates --glob '*.py' | head
test -f aiPlat-core/core/workspace_seeds/personas/security_coworker/PERSONA.md
rg -n 'attendanceInjectFields' packages/aiplat-pi-runtime/extensions/enterprise_approval.ts
# 认知分层旁路（§0.3）+ 任务语境闸门 P0
rg -n 'resolve_task_context|missing_task_context|build_llm_response_format' aiPlat-core --glob '*.py' | head
python3 scripts/generate_whitepaper_volumes.py --check
bash scripts/verify-whitepaper-ready.sh
```
