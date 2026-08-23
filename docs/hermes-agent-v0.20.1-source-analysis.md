# hermes-agent v0.20.1 源码级对标分析

> 源码：/Users/apple/workdata/person/openSource/hermes-agent-main/（NousResearch，MIT，v0.20.1）
> 主入口 run_agent.py（9005 行），真实 Agent 循环 agent/conversation_loop.py（8070 行）。以下每条结论均已 grep 验证。

## 维度清单（19 项）

1. **Agent 循环与执行模型 — ✅**
   单 turn 入口 `run_conversation()`（conversation_loop.py:1611），主循环 `while (api_call_count < max_iterations and agent.iteration_budget.remaining > 0)`（:1829），每轮 API 调用 = 一次迭代，`step_callback` 上报（:1881-1888）；事件经 `VALID_HOOKS` 插件钩子 + outbound_webhooks/reactions 外发。

2. **工具系统 — ✅**
   118 个 tools 模块，核心工具 ~60 个（toolsets.py:31-105 `_HERMES_CORE_TOOLS`），TOOLSETS 注册表（toolsets.py:107）；check_fn 条件启用且结果 30s 缓存、未通过的工具不进 schema（tools/registry.py:1021-1022）→ 零足迹成立；per-tool 审批回调。

3. **上下文管理 — ✅**
   三层 prompt：stable / context / volatile，明文注释"三层有序缓存层，会话内绝不重渲染以保 prompt cache 温热"（agent/system_prompt.py:338-346）；压缩 `run_compress_context_with_progress_timeout`（conversation_compression.py:822）、context_compressor.py；缓存标记 `PromptCachePlan`（agent/prompt_caching.py:21）。

4. **子代理与多 Agent 编排 — ✅**
   `delegate_task` 核心工具（toolsets.py:100）；单任务+批量并行（tools/delegate_tool.py:6）；`steer_subagent`/`interrupt_subagent`（delegate_tool.py:237,213）；worktree 隔离按配置开启、默认 False（delegate_tool.py:775-786）；子代理被禁止写共享 MEMORY.md（run_agent.py:1824）。

5. **Skill 系统 — ✅**
   `/skill` 命令扫描 `~/.hermes/skills/`（agent/skill_commands.py:403）；agentskills.io 标准格式（tools/skills_tool.py:28-42）；`skill_manage` 核心工具（toolsets.py:57）可运行时 `_create_skill`（tools/skill_manager_tool.py:908）；技能索引放 volatile 层（system_prompt.py:345）；渐进披露 = 索引进 prompt、正文按需 skill_view。

6. **学习闭环 — ✅ 完整**
   nudge：`_iters_since_skill >= _skill_nudge_interval` 触发（agent/codex_runtime.py:887-892）→ background_review 后台线程 fork（agent/background_review.py:1093，自动 deny 审批 667-681）→ 记忆/技能写入走 write_approval 门（tools/write_approval.py:24,114,253；tools/memory_tool.py:931）→ Curator 后台维护技能库（agent/curator.py:1,1496）。

7. **记忆系统 — ✅**
   `~/.hermes/state.db` SQLite + FTS5 全文检索（hermes_state.py:348,5,11）；`search_sessions`（hermes_state.py:10649）+ session_search 工具；MEMORY.md 个人笔记（tools/memory_tool.py:6,223）。

8. **规划 — ⚠️ 部分**
   `/goal`（set/draft/gate/status）+ 每 turn 结束 aux 模型 judge 判定完成（hermes_cli/goals.py:1239,4；cli_commands_mixin.py:2591）；但 `/plan` 不是命令而是普通 skill（skills/software-development/plan/SKILL.md:2），规划非强制。

9. **沙箱/权限/审批 — ⚠️ 部分**
   approvals.mode smart/manual/off + yolo（tools/approval.py:335-337,411）；smart = aux LLM 风险判定（approval.py:3216,4262）；hardline deny 规则先于 yolo/mode=off 绕过执行、不可绕过（approval.py:603）；写保护路径强制审批（agent/file_safety.py:219）。无隔离沙箱——terminal 类工具直接执行，靠审批门而非沙箱。

10. **会话持久化与恢复 — ✅**
    state.db SQLite（hermes_state.py:348）；`-r/--resume`（hermes_cli/main.py:578）+ 会话选择器（:1361）；压缩链续跑（:1582）；会话 fork API `POST /api/sessions/{id}/fork`（gateway/platforms/api_server.py:2074,3640）；parent_session_id 血缘（hermes_state.py:4458）。

11. **模型适配 — ✅**
    30+ ProviderConfig（hermes_cli/auth.py:250-495：anthropic/openai-codex/gemini/bedrock/vertex/azure-foundry/qwen/lmstudio/copilot…）；6 个原生 adapter（agent/anthropic_adapter.py 等）；Copilot 走 ACP 后端（agent/copilot_acp_client.py:1,73）；MoA 聚合（agent/moa_loop.py + run_agent.py:5143-5146 `build_moa_facade`）。

12. **多渠道/接口 — ✅**
    gateway 22+ 平台插件（plugins/platforms/：discord/slack/telegram/wecom/feishu/dingtalk/a2a…）+ 内置 adapter（api_server/signal/weixin/whatsapp_cloud…，gateway/platforms/）；REST+SSE API server（api_server.py:2064-2106）；ACP server（acp_adapter/entry.py:122）；MCP server（mcp_serve.py:1）；TS TUI（ui-tui/）+ Electron 桌面（apps/desktop/）。

13. **自修改/自我进化 — ⚠️ 部分**
    运行时创建/维护技能（skill_manager_tool.py:908）、Curator 增删合并技能（curator.py）；无修改自身源码/运行时代码的机制。

14. **扩展机制 — ✅**
    PluginContext 20+ 注册接口（hermes_cli/plugins.py:1388；register_tool/register_platform/register_command/register_memory_provider/register_hook…1662-3109）；VALID_HOOKS ~25 钩子（plugins.py:156）；shell-script hooks（agent/shell_hooks.py:4）；MCP 客户端工具（tools/mcp_tool.py）。

15. **【新增】协议面/可嵌入性 — ✅ 协议强、SDK 缺**
    `hermes-acp` = ACP agent server，JSON-RPC over stdio 持久内核（acp_adapter/entry.py:122,4）；REST+SSE sessions/chat/fork（api_server.py:2064-2077）；OpenAI 兼容 `/v1/chat/completions` + `/v1/responses`（:2088-2092）；MCP serve、A2A 插件；**无独立 pip/npm SDK**（pip 包即 CLI，pyproject.toml:364）；ACP session 提供会话原语（acp_adapter/session.py:159）。

16. **【新增】竞品资产导入 — ⚠️ 部分**
    AGENTS.md/CLAUDE.md/.cursorrules/SOUL.md 均作为上下文文件自动读取（agent/coding_context.py:82-86；prompt_builder.py:2323 CLAUDE.md、:2241 AGENTS.md 目录链）；skill 从 agentskills.io/GitHub 导入（hermes_cli/skills_hub.py）；MCP 配置导入（optional-mcps/）；hooks 配置导入（shell_hooks.py）；**无** Claude Code subagents/会话历史导入。

17. **【新增】执行引擎技术栈 — ✅**
    Python 3.11-3.13（pyproject.toml:15）；asyncio（api_server aiohttp + SSE）+ threading（`_MAX_TOOL_WORKERS=8` run_agent.py:265；bg-review 线程 run_agent.py:1843）；单进程为主、gateway 容器化部署（docker-compose.yml:29）；TUI/桌面为 TS/Electron。

18. **【新增】Thread/fork/steer/interrupt — ✅**
    `/steer` 中途转向：`AIAgent.steer`（run_agent.py:3367）+ 迭代间 drain（conversation_loop.py:1901-1918）+ 子代理 steer（delegate_tool.py:237）；fork 会话（api_server.py:3640 + 血缘 hermes_state.py:4458）；`interrupt`（run_agent.py:3166）+ `/stop` + `POST /v1/runs/{id}/stop`（api_server.py:2106）；无显式 Thread 对象，等价能力齐备。

19. **【新增】性能/优化机制 — ✅**
    推理保留：reasoning 以 `<think>` 标签嵌入 content 供轨迹存储（conversation_loop.py:1953；agent/trajectory.py:30）；压缩三路径：context_compressor.py / conversation_compression.py:822 / OpenAI Native Compaction 适配（agent/native_compaction.py:109）；prompt cache 三层缓存结构（system_prompt.py:338-346 + prompt_caching.py:21）。

## 标志性能力（源码证实）

1. **完整学习闭环**：nudge 计数 → 后台 review fork（自动 deny 审批）→ write_approval 门 → Curator 技能库维护，四环俱全（codex_runtime.py:887 / background_review.py:1093 / write_approval.py:114 / curator.py:1）。
2. **协议面最广的 agent 之一**：ACP stdio server + OpenAI 兼容 API + REST/SSE + MCP serve + A2A 五面（acp_adapter/entry.py:122 / api_server.py:2088 / mcp_serve.py:1 / plugins/platforms/a2a）。
3. **prompt cache 优先架构**：三层 stable/context/volatile 缓存设计 + 显式"绝不中途重渲染"纪律（system_prompt.py:338-346）。
4. **原生 compaction + 多路径压缩**：Native Compaction、自研压缩执行器带进度超时与持久化护栏（native_compaction.py:109 / conversation_compression.py:822）。
5. **30+ provider + MoA + Copilot-ACP 后端**（auth.py:250-495 / moa_loop.py / copilot_acp_client.py:1）。

## 明显限制（源码证实）

1. **无强制隔离沙箱**：审批制（smart/manual/off）而非沙箱，terminal 直接执行，hardline 仅保证 deny 不可绕过（approval.py:603,3216）。
2. **无独立 SDK**：可嵌入性全靠 ACP/REST 协议，无 pip/npm SDK 封装（pyproject.toml:364 仅 CLI）。
3. **自修改仅限技能层**：不改源码/运行时代码（skill_manager_tool.py:908 只建 skill）。
4. **规划非强制**：无 `/plan` 命令，plan 只是普通 skill，judge 为 fail-open（goals.py:18）。
5. **worktree 隔离默认关闭**、并行子代理无默认隔离（delegate_tool.py:775-786）；竞品 subagents/会话历史不可导入（维度 16）。

## 新增维度小结（aiPlat 可借鉴点）

- **协议面**：hermes-acp 的 JSON-RPC over stdio 持久内核即"app-server 式"嵌入通道，且叠加 OpenAI 兼容端点（`/v1/chat/completions`、`/v1/responses`）实现 SDK-less 集成——aiPlat 若做独立 SDK，可先补 ACP 或 OpenAI 兼容层即可被 Claude Code/Cursor 生态直接调用；Hermes 自身还反向消费 Copilot 的 ACP（copilot_acp_client.py:73），双向 ACP 值得借鉴。
- **导入面**：对 AGENTS.md/CLAUDE.md/.cursorrules 一视同仁读取（coding_context.py:82-86）比 Claude Code 只认 CLAUDE.md 更宽，成本低收益大；skills 走 agentskills.io 开放标准。
- **Thread 抽象**：无显式 Thread/Item 对象，用"会话 fork + parent_session_id 血缘 + steer/interrupt 运行时转向"实现等价能力（api_server.py:3640 / hermes_state.py:4458 / run_agent.py:3367）；若 aiPlat 要协议级 Thread/Turn 原语，可借鉴其"fork 即 lineage 分支、steer 即注入指令、interrupt 即取消"的最小实现。
