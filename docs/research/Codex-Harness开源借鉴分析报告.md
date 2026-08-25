# Codex Harness 开源借鉴分析报告

> **分析对象**：OpenAI 2026-08-19 开源的 `openai/codex`（Apache-2.0）——`codex-rs`（Rust 单体仓库，137 crate）、App Server（JSON-RPC over stdio 持久会话内核）、Codex SDK（TS/Python）、Thread/Turn/Item 三级抽象、平台原生沙箱、SQLite 状态持久化。
> **分析问题**：aiPlat（Python，43 万行 + 应用工厂 L2-L5）可以借鉴什么？哪些已有对应物、哪些是真缺口、借鉴优先级如何？
> **分析方法**：对 Codex Harness 的每个核心机制，先在 aiPlat 代码中搜索对应实现（附证据），再判定"已有/部分具备/真缺口"，最后给借鉴建议（成本阶梯）。
> **最后验证：2026-08-25**（verify 命令：grep 各维度代码证据；证据见各节）

---

## 0. 一句话结论

Codex Harness 开源对 aiPlat 的价值不在"它有什么能力"（aiPlat 大多已有对应物），而在**三个工程化姿势**：① 把运行时能力做成**可嵌入的公开协议**（app-server/JSON-RPC/SDK）——aiPlat 有内核但协议面薄；② **Thread/Turn/Item 三层抽象**显式化——aiPlat 的 run_events 事件流已具备同构数据，但未提升为产品级公开原语；③ **竞品资产非破坏性导入**是获客战略——aiPlat 已有 L2 代码导入 + format_adapters 格式桥，但缺"Agent 记忆/授权/会话"级导入。**最值得立即借鉴的是协议面（JSON-RPC app-server 式持久内核）+ 竞品导入收尾（会话/记忆级）**。

---

## 1. Codex Harness 核心机制 → aiPlat 对应物对照表

| # | Codex Harness 机制 | aiPlat 对应物（证据） | 判定 |
|---|---|---|---|
| 1 | **Thread/Turn/Item 三层抽象** | run_events 事件流（`pipeline_run_store.py:122` append-only 表 + `append_run_event`）+ **thread 协议公开（P0-a stdio 内核 `core/acp/stdio_server.py`：thread/start|status|events|resume|approve|reject|rollback|cancel 映射 PipelineSession + run_events，2026-08-24）** | ✅ **已补齐（2026-08-25）**：命名/协议已公开（thread=run 的协议别名，run_events 仍是唯一事件真相源） |
| 2 | **app-server：JSON-RPC over stdio 持久内核**（断连重连/steer/interrupt/审批） | ACP server（`core/acp/server.py`，FastAPI WebSocket）+ A2A（REST/SSE） | ✅ **已补齐（P0-a，2026-08-24）**：`core/acp/stdio_server.py` JSON-RPC over stdio 持久内核（thread/start|status|events|resume|approve|reject|rollback|cancel + 背压 -32001），入口 `python -m core.acp.stdio_server` |
| 3 | **codex exec：单次非交互入口** | P2-A7 no-agent script 模式（`event_loop.py:374` 判 `t.params.mode == "script"` 零 LLM 直接执行）+ 应用工厂双模式路由（`team_planner.py:50` mode: agent/code）——**有单次执行概念，但无独立 exec 命令/CI 入口** | ✅ **已补齐（2026-08-25）**：`aiplat exec` CLI（`aiplat-sdk/aiplat/exec.py` + `[project.scripts] aiplat`）：`aiplat exec "req"` 经 `StdioKernelClient` 跑流水线（thread/start→轮询 status→JSON）；`--script` 零 LLM fail-closed 白名单（bash/sh/python3/python，白名单外 exit_code=125） |
| 4 | **Codex SDK（TS/Python）程序化启停 Thread + 流式事件** | CoreFacade + REST API + **aiplat-sdk**（P1 stdio 客户端 + P2 exec CLI） | ✅ **已补齐（P1+P2，2026-08-24/25）**：`aiplat-sdk/aiplat/stdio.py`（StdioKernelClient 程序化启停 Thread + stream_events）+ `aiplat-sdk/aiplat/exec.py`（`aiplat exec` CLI，codex exec 对齐） |
| 5 | **平台原生沙箱**（Linux Bubblewrap+Landlock / macOS Seatbelt / Windows AppContainer） | SandboxGate（进程内检查式）+ pipeline_sandbox | ✅ **已补齐（P1，2026-08-24）**：`core/harness/infrastructure/os_sandbox.py`（bwrap/seatbelt 可选执行器：只读系统路径 + 可写工作区 + 默认网络隔离 + fail-open fallback，`AIPLAT_SANDBOX=bwrap/seatbelt`） |
| 6 | **SQLite 会话状态持久化 + thread/resume/fork** | SQLite 持久化（pipeline_runs + pipeline_run_events 双写）+ checkpoint（`langgraph/core.py:55` enable_checkpoints + record_checkpoint）+ 断点续跑（pipeline_engine HITL resume）——**持久化与恢复已具备**；fork/分支有 `ontology_branch.py`（本体层，非 Thread 层） | ✅ **已补齐（2026-08-25）**：`fork_run_from_events` 会话级 fork（折叠源事件→新 run 继承分叉点 + `pipeline_forked` 血缘事件，子 run 状态可纯从自身事件重建）+ `list_forked_runs` 血缘查询 + `POST /pipeline/pipelines/runs/{run_id}/fork`/`GET .../forks` |
| 7 | **人工审批协议**（approval request 暂停 Turn 等 allow） | ApprovalGate（`approval_gate.py:154`，危险命令检测 CRITICAL/HIGH/MEDIUM/LOW）+ HITL 事件驱动 resume（`pipeline_engine.py:587` v3.1）+ 前端 Approvals 页（`pages/Core/Learning/Approvals/Approvals.tsx`）——**审批闭环已具备** | ✅ 已有 |
| 8 | **背压机制**（过载返回 -32001 + 指数退避） | resilience_gate（`resilience_gate.py`，golden-ratio hash 退避抖动）+ rate_limit_tracker——**限流/退避已有**，但无协议层 -32001 语义 | ✅ **已补齐（2026-08-25）**：`BackpressureMiddleware`（`core/server.py`）inflight 超限 → **429 + Retry-After** 指数退避（2^overflow 上限 60s，`AIPLAT_BACKPRESSURE_MAX_INFLIGHT` 门控）；ACP WS 活跃连接超限 → 错误帧 `-32001` + 关闭码 1013；stdio 内核已有 -32001（P0-a）——三协议层语义统一 |
| 9 | **retained reasoning + context compaction**（ARC-AGI-3：13.3%→38.3%，token 1/6） | 5 级上下文压缩（`memory/compression.py:149` AGGRESSIVE 0.96-0.99 / EMERGENCY 0.99-1.0）+ 温度感知剪枝 + 语义相关性排序（P0-2/P0-3）+ 工具输出预算帽——**compaction 已深度实现**；retained reasoning 有近似物（`pipeline_engine.py:3201` <1KB 小输出保留，大输出 stub） | ✅ 已有（compaction）/ ⚠️ retained 部分 |
| 10 | **竞品资产非破坏性导入**（Claude Code/Cursor→AGENTS/CLAUDE.md、Skills、MCP、Hooks、subagents、30 天会话） | L2 import-repo + format_adapters + claude_md 上下文引擎 + **P0-b 会话/记忆级导入** | ✅ **已补齐（P0-b，2026-08-24）**：`core/harness/memory/import_claude_sessions.py`（Claude JSONL 会话→MemoryManager，source_tag=claude_import + provenance 防投毒溯源，只读消费不动源文件）——**会话/记忆级导入落地**，授权级（凭据迁移）为安全边界内保留项 |
| 11 | **扩展体系**（tools/MCP/skills/plugins/hooks） | 全齐：MCP（`apps/mcp/` 8 文件 server/client/protocol）、Hooks（`infrastructure/hooks/` 7 文件含 G6 cc_bridge）、Skills（engine/workspace + agentskills.io）、plugins（`apps/plugins/manager.py`） | ✅ 已有 |
| 12 | **137 crate 模块化单体（Rust）** | Python 单体 + 模块化（harness/apps/services/api）+ pipeline_engine 拆分 5 Mixin（P2-A4）——**语言不同但模块化治理已有** | ✅ 已有（姿势不同） |

---

## 2. 真缺口与借鉴优先级

### P0（建议尽快做，成本低/中，收益明确）

**2.1 协议面：app-server 式 JSON-RPC over stdio 持久内核（❌ 真缺口）**

现状：ACP server 是 WebSocket 版（`core/acp/server.py`），面向 IDE；**无 stdio JSON-RPC 持久会话内核**——即"外部程序/CI/运维面板可 spawn 一个 aiPlat 内核进程，通过 stdin/stdout JSON 行驱动 Thread，断线后 thread/resume 恢复"。

借鉴价值：Codex 的 app-server 把"会话/审批/steer"从黑盒变成可嵌入协议——aiPlat 的审批（ApprovalGate + HITL resume）和事件流（run_events）都已就绪，**缺的只是把已有内核能力暴露为 stdio JSON-RPC 协议层**（类似 ACP 但更薄、面向程序而非 IDE）。

成本估算：中（1-2 天）——可复用 ACP server 的 handler 逻辑，新增 thread/start、thread/resume、item.event 流式 + approval.request/allow/deny 方法（均为**拟新增协议方法名**，非现有代码），映射到已有 run_events/HITL。

接线点：`core/acp/`（新增 `stdio_server.py`）+ `CoreFacade`（方法映射）。

**2.2 竞品导入收尾：会话/记忆/授权级导入（⚠️ 部分具备）**

现状：L2 import-repo 导入**代码**；format_adapters 导入 **AGENT.md/SKILL.md/MCP 配置**；claude_md 引擎读取 **CLAUDE.md**。但 Codex 导入的还有：**近 30 天会话历史、MCP 授权状态、slash command、subagent 定义**——即"Agent 记忆"。

借鉴价值：aiPlat 记忆系统（四层 MemoryManager + SQLite long_term_memories）已有载体；缺的是"从 Claude Code/Cursor 会话导出 JSONL → aiPlat episodic/semantic 记忆"的导入通道（类似 L2 之于代码）。

成本估算：低-中（1-2 天）——Claude Code 会话导出是 JSONL（`~/.claude/projects/*.jsonl`），解析后灌入 MemoryManager.save_interaction 即可；顺带把 skills 导入已有通道（agentskills.io）复用。

接线点：`core/harness/memory/`（新增 `import_claude_sessions.py`）+ platform 端点（`POST /memory/import`）。

### P1（建议后续做，成本中/高）

**2.3 SDK 包（TS/Python）（❌ 真缺口）**

现状：CoreFacade 是进程内门面，REST 是 HTTP 面；**无 pip/npm 包**让外部程序程序化启停 run + 流式监听事件。

借鉴价值：Codex SDK 让"在你的代码里启停 Thread"成为一行 import。aiPlat 若做 `aiplat-sdk`（Python 优先），本质是**把已有 REST 端点封装成类型化客户端 + 事件订阅**（SSE/WS 已有），成本不高但需要独立包维护。

成本估算：中（2-3 天，Python 包 + 事件订阅封装 + 示例）。

**2.4 OS 原生沙箱升级（⚠️ 部分具备）**

现状：SandboxGate 是进程内检查（路径/网络/限流），非 OS 隔离——恶意命令在 gate 通过后仍以进程身份执行。

借鉴价值：Codex 用 Bubblewrap/Seatbelt 做真隔离。aiPlat 可先做 **Linux bubblewrap 可选执行器**（`AIPLAT_SANDBOX=bwrap` 时命令执行包 bwrap 参数，保留现有 subprocess 调用链为 fallback——与方案 B fail-open 哲学一致）。

成本估算：中-高（3-5 天，含跨平台探测 + 降级链 + 测试）。

### P2（参考方向，不急于做）

- **~~Thread/fork 会话级分支~~（✅ 已实施 2026-08-25）**：`fork_run_from_events` 折叠源 run 事件 → 新 run 继承分叉点（stage/pass_rate）并从 executing 继续；`pipeline_forked` 事件（append-only，含 parent_run_id + 继承状态）使**子 run 状态可纯从自身事件重建**（`replay_run_events` 折叠该事件）；`list_forked_runs` 血缘查询；`POST /pipeline/pipelines/runs/{run_id}/fork` + `GET .../forks`。测试 3 例（继承+purity / 无事件 None / 血缘逆序+limit），`test_pipeline_run_events.py` 9 例全绿。
- **~~协议级背压 -32001 语义~~（✅ 已实施 2026-08-25）**：`BackpressureMiddleware`（`core/server.py`）——全局 inflight 并发计数，`AIPLAT_BACKPRESSURE_MAX_INFLIGHT>0` 时超限请求返回 **429 + Retry-After**（`_backpressure_retry_after` 指数退避 2^overflow，上限 60s，对齐 codex -32001）；`backpressure_stats()` 诊断。ACP WS 层：`AIPLAT_ACP_MAX_CONNECTIONS>0` 时活跃连接超限拒绝新连接（错误帧 `-32001` + 关闭码 1013）。三协议层语义统一：HTTP=Retry-After 头、WS/stdio=-32001。测试 5 例（`test_backpressure_protocol.py`）。
- **~~exec 单次入口命令~~（✅ 已实施 2026-08-25）**：`aiplat exec` CLI（`aiplat-sdk/aiplat/exec.py` + pyproject `[project.scripts] aiplat`）——默认流水线模式：`aiplat exec "requirement"` 经 `StdioKernelClient` spawn stdio 内核 → `thread/start` → 轮询 `thread/status` 直到 done（超时 best-effort cancel），返回最终状态 JSON；`--script` 模式零 LLM 直接 subprocess（对齐 P2-A7 fail-closed 入口白名单 bash/sh/python3/python，白名单外 exit_code=125 拒绝，绝不静默 fallback）。`aiplat.__init__` 导出 `exec_script`/`exec_pipeline`/`exec_main`。测试 8 例（`test_exec_cli.py`）。

---

## 3. 已对齐项确认（无需借鉴，保持即可）

| Codex 机制 | aiPlat 现状 | 结论 |
|---|---|---|
| 审批流 | ApprovalGate + HITL v3.1 事件驱动 resume + 前端 Approvals 页 | ✅ 已对齐（甚至更完整：四档危险分级） |
| context compaction | 5 级压缩 + 温度剪枝 + 语义排序 + 预算帽 | ✅ 已对齐（Codex 的核心优化 aiPlat 已有深度实现） |
| 扩展体系 | MCP/Hooks（含 G6 桥）/Skills/plugins 全齐 | ✅ 已对齐 |
| SQLite 持久化 + resume | run 双写 + checkpoint + 断点续跑 | ✅ 已对齐 |
| 模块化单体 | pipeline 拆分 5 Mixin + 模块边界 | ✅ 已对齐（姿势） |

---

## 4. 战略层借鉴（Codex 开源 = "Agent 从产品变平台"）

Codex 开源的战略是**两手**：① 把 runtime 开放成可嵌入协议（拉新开发者）；② 竞品资产一键迁入（撬存量用户）。aiPlat 的对标动作：

- **协议面是当前最薄处**：aiPlat 内核能力（审批/事件/记忆/沙箱）远超协议面暴露。P0 的 stdio JSON-RPC 内核 + P1 的 SDK 是把"能力"变成"平台"的关键两步——与 Codex app-server 开源同构。
- **导入战略已有底座**：L2 代码导入 + format_adapters 格式桥是"资产迁入"的前半段；补齐**会话/记忆级导入**（P0-2.2）即完成 Codex 式"整包搬进"。
- **不借鉴的**：Rust 重写（aiPlat Python 生态与 DI/门面治理成熟，语言是姿势差异非能力差异）；模型绑定（aiPlat 模型无关是差异化优势，保持）。

---

## 5. 结论

aiPlat 与 Codex Harness 的能力差距**不在内核，在协议面**：
- 内核层（审批/压缩/持久化/扩展/沙箱检查）：**已对齐或部分具备**，无需大改；
- 协议层（app-server/SDK/exec）：**真缺口 2 项**（stdio JSON-RPC 内核、官方 SDK），是"产品→平台"的关键；
- 导入层：**收尾 1 项**（会话/记忆级导入），复用已有 format_adapters + MemoryManager 即可。

**建议批次**：P0-a stdio JSON-RPC 内核（复用 ACP handler + run_events/HITL）→ P0-b 会话/记忆导入（复用 format_adapters + MemoryManager）→ P1 SDK 包 → P1 OS 沙箱可选执行器。全程 clause-sync + acceptance 登记。
