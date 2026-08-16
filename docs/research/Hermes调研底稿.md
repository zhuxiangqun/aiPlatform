# Hermes Agent 核心能力清单（调研报告）

> 调研对象：Nous Research / hermes-agent（GitHub: NousResearch/hermes-agent，"The agent that grows with you"）
> 调研方式：web_search + 直接抓取 GitHub API（仓库元数据实测）、GitHub README、官方文档站全文（llms-full 3.7MB 已全文检索）
> 调研时点：2026-08-15（GitHub API updated_at 一致）；所有引用的 docs URL 均已验证 HTTP 200
> 用途：与 aiPlat、DeepSeek Harness、Claude Code 三方能力对标（主报告：`aiPlat核心能力对标报告.md`）
> 说明：本文件为对标调研底稿，供复核追溯；核心结论已整合进主报告。

## 0. 一句话定位（修正版）

Hermes 是 Nous Research 开源的**个人/团队级自我进化 Agent**：单一 AIAgent 核心循环驱动 CLI/Gateway(20+ IM 平台)/ACP/API Server/Python 库全部入口；核心差异化 = **内建学习闭环（后台 review → 记忆/技能写入 → 可选审批发布）+ 三层持久记忆 + 7 种终端执行后端 + 统一 Gateway 多渠道**。MIT 协议，Python，当前 v0.20.1。

> ⚠️ **归属修正**：hermes-agent 仓库属于 **NousResearch**，不是 plastic-labs。plastic-labs 的 Honcho（辩证用户建模）以 **memory provider 插件**形式集成（`plugins/memory/honcho/`）。
> 对比文档 docs/archive/aiPlat-architecture-compare.md 的定位描述经最新一手资料核实**基本准确**。

## 1. Agent 循环与执行模型（AIAgent Core Loop）

- `run_agent.py` 的 **AIAgent 类**（~9200 行）驱动全部入口：CLI、Gateway、ACP、Batch Runner、API Server、Python Library
- 接口：`chat()`（简单）与 `run_conversation()`（完整，返回 messages/metadata/usage）；turn 生命周期含可中断模型调用、线程池并发工具执行、fallback 模型切换、跨 parent/child 迭代预算（iteration budget）
- API 模式 3 种：`chat_completions`（OpenAI 兼容）/ `codex_responses` / `anthropic_messages`，内部统一为 OpenAI 风格消息格式
- **执行后端 7 种**：local / docker / ssh / singularity / modal / daytona / vercel_sandbox；Browser 5 种；Web 4 种；MCP 动态加载
- 成熟度：**成熟核心 + 快速扩张边缘**（AGENTS.md 明示 "narrow waist"：新增核心工具高门槛，优先 CLI+skill → service-gated tool → plugin → MCP）

来源：
- https://github.com/NousResearch/hermes-agent
- https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop
- https://hermes-agent.nousresearch.com/docs/developer-guide/architecture

## 2. 工具系统（Tools Runtime + Toolsets）

- 注册模型：`registry.register(name, toolset, schema, handler, check_fn, requires_env, is_async, ...)`；跨 toolset 同名注册被拒
- **AST 自动发现**：`discover_builtin_tools()` 扫 `tools/*.py` 顶层 `registry.register()`，新增工具文件零手工登记
- **70+ 内置工具、28 个 toolsets**（架构文档口径；README"40+"为滞后文案）；toolset 按平台启用/禁用、平台预设（hermes-cli/hermes-telegram）、MCP 动态 mcp-<server>
- 覆盖：web/terminal/file/browser/media/编排（memory/delegate_task/cron）/homeassistant

来源：
- https://hermes-agent.nousresearch.com/docs/user-guide/features/tools
- https://hermes-agent.nousresearch.com/docs/developer-guide/architecture
- https://github.com/NousResearch/hermes-agent/blob/main/AGENTS.md

成熟度：**工具体系成熟、扩展机制清晰**（自注册+AST 发现+toolset 门控+服务门控 check_fn），与 aiPlat 工具阶梯理念高度同构。

## 3. 上下文管理（Prompt Build + Cache + Compression）

- Prompt 组装**三层分级**：`stable`（SOUL.md 身份、工具/模型指引、skills 索引）→ `context`（system_message + 项目上下文文件）→ `volatile`（MEMORY.md/USER.md 快照、时间戳/会话/模型行）
- Context Files 第一匹配优先：`.hermes.md`/`HERMES.md` → `AGENTS.md` → `CLAUDE.md` → `.cursorrules`
- **Prompt caching 为"神圣"设计铁律**（与 aiPlat "Prompt Cache 不可侵犯"同构）：不中途改 system prompt 前缀、不换 toolsets、不重建上下文结构
- **双压缩系统**：Gateway Session Hygiene（85% 上下文阈值安全网）+ Agent ContextCompressor（50% 阈值真实 token）；`ContextEngine` ABC 可插拔（如 lcm 无损上下文插件）

来源：
- https://hermes-agent.nousresearch.com/docs/developer-guide/prompt-assembly
- https://hermes-agent.nousresearch.com/docs/developer-guide/context-compression-and-caching
- https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files

成熟度：**成熟且设计克制**。

## 4. 子代理（Subagent Delegation）

- `delegate_task` spawn 子 AIAgent：**完全隔离上下文**（fresh conversation，子代理零知识，只拿 parent 填充的 `goal`+`context`，只回最终摘要）；继承工具访问、独立 terminal session
- 并行 batch（默认 3 并发可配置）；orchestrator 角色等待 workers 合成
- `max_spawn_depth` 1-3（默认 1=扁平）；`worktree_isolation`（每子代理独立 git worktree）
- 模型路由：默认继承 parent provider/model；可配 delegation.provider/model 或直连端点（api_mode 自动探测）

来源：
- https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
- https://github.com/NousResearch/hermes-agent

成熟度：**成熟**（"Subagents Know Nothing" 隔离语义明确）。

## 5. Skill 系统（Skills System）

- `~/.hermes/skills/` 为唯一事实源；兼容 **agentskills.io 开放标准**（结构化 Markdown + metadata）；支持外部 skill 目录
- **渐进式披露**省 token：`skills_list()`（紧凑索引 ~3k tokens，会话开始加载）→ `skill_view(name)`（完整 SKILL.md 按需加载）；技能即 slash command、单消息可叠加最多 5 个
- `skill_manage` 工具（create/patch/edit/delete/write_file/remove_file，patch 优先）；`/learn` 自动生成技能；skill bundles；**Skills Hub**（agentskills.io 检索/安装）；`hermes skills` CLI（publish/tap/snapshot/audit）

来源：
- https://hermes-agent.nousresearch.com/docs/user-guide/features/skills

成熟度：**成熟且是核心卖点之一**。

## 6. 学习闭环（Learning Loop）★标志性能力

任务描述的"反馈→eval→技能草案→发布"按真实流程校准如下：

| 阶段 | 机制 |
|---|---|
| 触发（nudge） | 后台 self-improvement 阈值：**每 10 个用户 prompt → memory review**；单 turn 每 10 次工具迭代 → skill review；`_spawn_background_review()` 分叉 review agent |
| 判断（≈eval） | review agent 判断"是否值得沉淀"（重复修正/弯路/用户纠正→技能；持久事实/偏好→记忆）。**官方文档未见独立离线 eval 评分器——待确认** |
| 写入（草案） | 统一走 `memory`/`skill_manage` 工具；默认自由写入即时生效（技能=procedural memory，记忆=durable facts） |
| 审批发布 | `skills.write_approval: true` → 暂存 `~/.hermes/pending/skills/` → `/skills pending|diff|approve|reject` → 通过才生效；memory 同款 gate；可选内容安全扫描 guard_agent_created |
| 维护 | **Curator** 后台维护 agent 创建技能：按使用频率 active→stale→archived，auxiliary review 提议合并/修补漂移（防技能堆积） |
| 成本控制 | review 可路由便宜模型，利用主模型 warm prompt cache 低成本重放；consent-aware（默认 💾 通知） |

来源：
- https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
- https://hermes-agent.nousresearch.com/docs/user-guide/features/memory
- https://hermes-agent.nousresearch.com/docs/user-guide/features/curator
- https://hermes-agent.ai/blog/self-improving-ai-guide

成熟度：**最成熟/最独特的差异化能力**；"eval"环节由 review agent 的 LLM 判断承担（无公开独立评分器，待确认）。

## 7. 记忆系统（四层）

| 层 | 内容 |
|---|---|
| L1 SQLite 会话/状态 | `~/.hermes/state.db`（WAL）：sessions/messages/session_model_usage/messages_fts（FTS5+trigram(CJK)+cjk_unicode61）/gateway_routing/compression_locks/async_delegations；parent_session_id 谱系链；source 标签（cli/telegram/discord...） |
| L2 策展持久记忆 | `MEMORY.md`（2,200 字符 ~800 tokens）+ `USER.md`（1,375 字符），会话开始**冻结快照**注入 system prompt（保前缀缓存）；超限报错而非静默丢 |
| L3 跨会话检索 | `session_search` 工具：FTS5 全文检索、**无 LLM 调用**；discovery（query+bookend 重构 goal→match→resolution，15-50ms）+ scroll 两形态 |
| L4 外部 MemoryProvider | 可插拔插件：Honcho（plastic-labs）/Mem0/Hindsight/Supermemory/RetainDB/ByteRover/OpenViking/Holographic 等 8+ |

来源：
- https://hermes-agent.nousresearch.com/docs/developer-guide/session-storage
- https://hermes-agent.nousresearch.com/docs/user-guide/features/memory
- https://hermes-agent.nousresearch.com/docs/user-guide/features/honcho

成熟度：**成熟、分层清晰**（README"LLM summarization"与检索"无 LLM"表述并存，细节待确认）。

## 8. 规划（Planning）

- `/plan` skill：先写 markdown 实现计划到 `.hermes/plans/`，而非直接执行
- **`/goal` Persistent Goals**：Ralph loop 风格，每 turn 用轻量 judge model 判断目标达成，未达成自动把 continuation 喂回同一会话继续，直到达成/暂停/清空/预算耗尽；官方明示受 Codex CLI `/goal` 启发
- Kanban 多 Agent 任务板（Multi-Agent Board，`hermes kanban`）

来源：
- https://hermes-agent.nousresearch.com/docs/user-guide/features/goals
- https://hermes-agent.nousresearch.com/docs/user-guide/features/skills

成熟度：**中等偏成熟**（skill 化 + 持续目标循环 + 看板，非独立 planner 组件）。

## 9. 沙箱 / 权限 / 审批

- **八层安全模型**：① 用户授权（allowlist + DM pairing）② 危险命令审批（HITL）③ 文件写入安全（denylist + write sandbox）④ 容器隔离（Docker/Singularity/Modal）⑤ MCP 凭据过滤 ⑥ context file 注入扫描 ⑦ 跨会话隔离 ⑧ 输入清洗
- `approvals.mode`: **smart**（默认，auxiliary LLM 评估风险）/ manual / off；`cron_mode: deny`；破坏性 slash 命令三选确认框
- 工具级 check_fn 服务门控（未配置=0 成本）

来源：
- https://hermes-agent.nousresearch.com/docs/user-guide/security

成熟度：**成熟但偏"个人使用"强度**——无企业级策略引擎/角色 RBAC/审计留痕平台化（轻治理，与 aiPlat PolicyGate+ApprovalGate 定位不同）。

## 10. 多渠道入口（CLI / Gateway / ACP）

- CLI/TUI + **Gateway 20+ 平台**：Telegram/Discord/Slack/WhatsApp/Signal/SMS/Email/Home Assistant/Mattermost/Matrix/DingTalk/Feishu/WeCom/Weixin/BlueBubbles/QQ/Yuanbao/Teams/LINE/ntfy/browser + 插件（IRC/Buzz/SimpleX/Google Chat 等）；统一 session（key `agent:main:{platform}:{chat_type}:{chat_id}`）、跨平台续聊；网关内跑 cron（60s tick）
- **ACP**（Agent Client Protocol，stdio JSON-RPC，VS Code/Zed/JetBrains）+ TUI gateway（JSON-RPC/WS）+ **API Server**（OpenAI 兼容 HTTP+SSE）+ Python library
- 内置 `hermes claw migrate` 从 OpenClaw 迁移

来源：
- https://hermes-agent.nousresearch.com/docs/user-guide/messaging
- https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration

成熟度：**多渠道是另一大招牌**，Gateway 平台矩阵广度在开源 agent 中罕见。

## 11. 模型适配（LLM Providers Resolver）

- **共享 resolver**：CLI/gateway/cron/ACP/auxiliary 全部走同一解析链（`hermes_cli/runtime_provider.py` + `providers/` ABC + 插件化 `plugins/model-providers/`）
- 优先级：显式请求 → config.yaml → env → provider 默认
- **30+ provider 家族**：Nous Portal/OpenRouter/OpenAI（含 Codex）/Anthropic/Google/DashScope/DeepSeek/Z.AI/Kimi/MiniMax/Bedrock/Azure/xAI/HuggingFace/Ollama Cloud/LM Studio/Custom 等；3 种 wire 协议自动探测；fallback 模型；**MoA 虚拟 provider**（多模型投票+聚合器）

来源：
- https://hermes-agent.nousresearch.com/docs/developer-guide/provider-runtime
- https://hermes-agent.nousresearch.com/docs/integrations/providers
- https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents

成熟度：**成熟、插件化程度高**（新增 provider=放插件目录，resolver 零分支），与 aiPlat 模型解析中心化同构。

## 12. 自我进化能力（Self-Improving）

- 官方口号 "The agent that grows with you" / "only agent with a built-in learning loop"
- 三通道：① 技能自生成（skill_manage 沉淀）② 技能使用中自改进（patch）③ 记忆/画像累积（nudge + USER.md）
- 改进发生在 **agent 层上下文**（记忆/技能/会话轨迹），**非模型权重**（官方博客明示无需 retrain）
- 研究向：Batch 轨迹生成 + 轨迹压缩（ShareGPT 格式）供 RL/微调训练

来源：
- https://github.com/NousResearch/hermes-agent
- https://hermes-agent.ai/blog/self-improving-ai-guide
- https://hermes-agent.nousresearch.com/docs/user-guide/features/batch-processing

成熟度：**最大卖点，三方对标最该关注的差异化**。

## 13. Cron 调度、Insights 等外围能力

- **Cron**：`cronjob` 工具 + `hermes cron` CLI + 自然语言创建；一次性/周期；结果投递任意平台；**no-agent 模式**（纯脚本定时执行，零 LLM）；模型解析 per-job pin → cron.model → 全局默认（fail-closed 防静默切换付费模型）；cron 内禁止递归建 cron
- **Insights**：`hermes insights [--days N] [--source]` token 用量/成本/工具分布/活跃分析
- 会话管理：/compress /undo /retry /stop、hermes sessions（repair-routing 等）
- 其他：MCP（stdio/HTTP/OAuth）、Voice Mode、Document Extraction、LSP 语义诊断、Personality & SOUL.md、四类插件（Provider/Context Engine/Platform/Memory）、Hermes Relay、OpenClaw 迁移

来源：
- https://hermes-agent.nousresearch.com/docs/user-guide/features/cron
- https://hermes-agent.nousresearch.com/docs/reference/cli-commands
- https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp

成熟度：**外围能力面很宽**；Insights 是 CLI 分析命令，非平台级可观测性（无事件总线/审计留痕，与 aiPlat run_events/syscall_events 定位不同）。

## 14. 开源状态（2026-08-15 GitHub API 实测）

| 项 | 数据 |
|---|---|
| 仓库 | NousResearch/hermes-agent |
| Stars | **230,763**（2026-08-15 快照；公开 6 周达 57,200，增速约 5,000/周） |
| Forks / Watchers | 45,749 / 884 |
| License | **MIT** |
| 语言 | Python |
| 创建/公开 | repo 创建 2025-07-22；**公开发布 2026-02-25** |
| 当前版本 | **v0.20.1（2026.8.13）**；约每月 2-3 版 |
| Issues | ~32,100 open |
| 生态（2026-04） | 80+ 质量过滤生态仓库：3 官方扩展、17 社区技能库（含 4,132-star Anthropic Cybersecurity Skills 集合）、8 外部记忆 provider、9 多 agent 编排框架、7 部署模板 |

来源：
- https://api.github.com/repos/NousResearch/hermes-agent
- https://github.com/NousResearch/hermes-agent
- https://hermesatlas.com/reports/state-of-hermes-april-2026

成熟度：**现象级开源热度 + 高速迭代**（230K stars 为调研时点快照）。

## 附：存疑/待确认清单

| # | 事项 | 说明 |
|---|---|---|
| 1 | plastic-labs 归属 | hermes-agent 仓库属 NousResearch；plastic-labs 以 Honcho（memory provider 插件）参与生态 |
| 2 | 工具数量口径 | README"40+ tools" vs 架构文档"70+ tools / 28 toolsets"——以架构文档为准 |
| 3 | Terminal 后端数量 | README 7 种 vs 架构图示 6 种（旧图）——以 7 种为准 |
| 4 | 学习闭环的 "eval" | 官方文档无独立 eval 评分器；"评估"由后台 review agent 判断承担；隐藏校验步骤：**待确认** |
| 5 | session_search 的 LLM 摘要 | 检索文档"无 LLM" vs README"LLM summarization"——分别指检索本体与辅助摘要，细节**待确认** |
| 6 | Stars 增速 | 230K+ 为 2026-08-15 快照（两次 API 调用一致 230,762→230,763） |

## 与 aiPlat 对标的三点直接结论

1. **Hermes 最强差异化 = 学习闭环 + 多渠道 Gateway + 7 执行后端**；aiPlat 若对标，学习闭环（nudge→review→写入门控→审批发布→Curator 维护）是最值得吸收的机制设计。
2. **Hermes 弱项 = 治理平台化**（审批是交互式 HITL，无可观测事件总线/审计留痕/发布灰度）——正是 aiPlat 的增强区。
3. **设计哲学高度趋同**：prompt cache 神圣化、narrow waist/工具阶梯、模型解析中心化——三方（aiPlat/Hermes/Claude Code）在架构约束上已形成共识。
