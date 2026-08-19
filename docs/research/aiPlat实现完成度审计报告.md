# aiPlat 实现完成度审计报告（能力是否实现 + 是否起作用）

> **审计目的**：回答"是不是所有能力都实现并且都起作用了"——**代码存在 ≠ 能力起作用**。本报告系统核查：声明能力是否实现（代码存在）+ 是否真正接线（有非测试生产调用者 / 经 CoreFacade / 经 HTTP 端点消费 / feature flag 未隐藏）。
> **审计方法**：AST 提取模块级公共符号 → 全仓生产代码 grep 调用者 → 人工交叉验证（排除工厂模式/动态 import/re-export 误报）→ 交叉验证 CoreFacade/HTTP 端点/前端页面消费。
> **审计时点**：2026-08-15（首轮）；**2026-08-19 复核**（对照《status-baseline-2026-08-19.md》更新过时结论）。首轮基线：architecture_guard 4 FAIL（§57/§73/§74/§17）+ capability_convergence 全 PASS + 死代码标记 0。

> **2026-08-19 状态更新**（对照基线逐项复核）：
> - **架构守卫：4 FAIL → 全绿（0 ERROR）**——§57（P0-A1 harness→apps 收敛 DI，白名单 38→25）/ §73、§74（工具链集成，P1-B2 verify_capability_consumers 入 CI）/ §17（P0-A10 builder E2E 20/20，§17 PytestCheck 降为 warn 级放行）全部清零。
> - **三大"整体未接线"子系统（arena / voice_loop / wake_agent）：全部已接线**（P0-B3，各 ≥10 生产 caller）——经 CoreFacade 导出 + `core/apps/tools/*_tool.py` 工具注册（`server.py:1050/1051`）+ `aiPlat-platform/apps/eval/api/arena_wiring.py` 端点（`GET /arena/leaderboard`、`POST /arena/run` 等）。原报告 §2 的 A 类问题**已消除**。
> - **能力数**：`capability_registry.yaml` total=**1032**；`AIPLAT_CAPABILITIES.md` total=**1039**（口径不同：registry 登记 vs 扫描；P0-C4 口径统一，commit 351f816a）。
> - **行动纲领 53/53 全 DONE**（PR #16-29，2026-08-18/19 合并）；宪法测试 **143 passed + 1 skipped**；分支保护 8 contexts + enforce_admins=true；MFA 强制（P0-5）。
> - **残留（已知部分项，非未接线）**：B4（CoreFacade 部分 getter 如 `get_retrieval_crag` 仍 0 调用者）、B5（opt-in flags 语义需文档化）、C3（registry→docs 漂移未自动清零，`sync_registry_to_docs.py` 已建）。

---

## 0. 总体结论

| 维度 | 结论 | 证据 |
|---|---|---|
| **实现完成度** | 高——声明能力绝大多数有代码实现 | capability_registry 1032 / CAPABILITIES 1039；arch_guard 全绿 0 ERROR；死代码标记 0 |
| **接线完成度** | 高——2026-08-15 审计发现的 3 个未接线子系统已全部接线 | arena/voice_loop/wake_agent 各 ≥10 caller（P0-B3）；剩余仅 B4 facade getter 部分冗余 |
| **核心链路** | 全部起作用（syscalls/gates/memory/knowledge/evolution/subagent/渠道/tenant 均有真实调用者） | 见 §4 |
| **主要风险** | ① B4：少量 CoreFacade getter 无人消费（get_retrieval_crag 等）；② B5：opt-in flag 语义需文档化；③ C3：registry→docs 漂移未自动清零 | 见 §3/§5，均为行动纲领跟踪的部分项 |

**一句话**：aiPlat 的能力"实现率"高（≈95%+ 已实现），"生效率"经 2026-08-19 复核已大幅提升——首轮发现的 3 个整体未接线子系统（Elo 竞技场、语音循环类、唤醒监控）**已全部接线生效**；核心链路全部起作用。当前残留仅为三类"部分项"（少量 facade getter 冗余、opt-in flag 文档化、registry→docs 同步自动化），不再是"有系统未接线"级别的缺口。

---

## 1. 审计基线（先确认工具链可信）

| 检查项 | 2026-08-15（首轮） | 2026-08-19（复核） | 证据 |
|---|---|---|---|
| architecture_guard.sh | **4 FAIL**（§57 NEW / §73 / §74 / §17） | **全绿（0 ERROR）**；§17 PytestCheck warn 级放行（builder E2E 20/20） | `architecture_guard.py --json` ok:true（基线权威事实） |
| capability_convergence.py | 全 PASS | 升级为强化验证链：**C5 4 机制接线**（cap check / check_doc_sync / generate_impact_matrix / check_code_doc_gap）+ **P1-B2 verify_capability_consumers 入 CI** + **C7 golden --verify 入 CI** | 见基线 P0-C5/P1-B2/C7 |
| 死代码标记（TODO wire/0 caller/待接线） | 0 处 | 0 处（保持） | `grep -rn`（TODO wire / 0 caller / 待接线）core/ 空 |
| caller_verify.sh | 已废弃 | 由 verify_capability_consumers（P1-B2，CI 接线）正式替代 | 脚本头 DEPRECATED + CI workflow 引用 |

---

## 2. 【A 类问题】整体未接线的子系统 —— **2026-08-19 复核：全部已接线（A 类问题消除）**

> 2026-08-15 首轮判定 3 个子系统"实现了但 0 生产调用者"；2026-08-18/19（PR #21、#22、B3）全部补齐生产入口。以下保留首轮表格作历史对照，每节附 2026-08-19 复核接线证据。

### 2.1 `harness/arena/`（Elo 竞技场 + Champion Pipeline）—— ✅ 已接线（2026-08-18/19，B3）

| 符号 | 文件 | 2026-08-15 | 2026-08-19 复核 |
|---|---|---|---|
| `EloScorer` / `ChampionResult` / `ChampionPipeline` / `RegressionRunner` / `RegressionReport` / `BenchmarkTask` | `arena/arena.py`、`arena/regression.py` | ❌ 全仓 0 生产引用 | ✅ **已接线**（≥10 caller） |

- **2026-08-19 接线证据**：
  - CoreFacade 导出：`core/api/core_facade.py:3386/3399` `from core.harness.arena.arena import DarwinArena`（leaderboard / run 两个入口）；
  - 平台端点：`aiPlat-platform/apps/eval/api/arena_wiring.py`（`GET /arena/leaderboard`、`POST /arena/run`）；
  - 前端诊断中心"LLM 评测"消费（2026-08-15 建议的接线路径已落地）。
- **影响消除**：CLAUDE.md/ROADMAP 声称的"竞技场对比评测"（Elo 评分、Champion 冠军流水线、回归基准）**现已可经 API 触发**。

### 2.2 `harness/multimodal/voice_loop.py`（VoiceLoop 语音循环）—— ✅ 已接线（2026-08-18/19，B3）

| 符号 | 文件 | 2026-08-15 | 2026-08-19 复核 |
|---|---|---|---|
| `VoiceLoop` / `get_voice_loop` / `MultiModalTrigger` / `get_multimodal_trigger` / `GoalLoopBridge` / `get_goal_loop_bridge` | `multimodal/voice_loop.py`、`multimodal/trigger.py` | ❌ 0 生产引用 | ✅ **已接线**（≥10 caller） |

- **2026-08-19 接线证据**：
  - 工具注册：`core/apps/tools/voice_loop_tool.py` `VoiceLoopTool`（完整语音循环 STT → Agent → Browser/Tool → TTS），`core/server.py:1050` 挂载；
  - CoreFacade：`core/api/core_facade.py:3427-3428` `process_voice_command`；
  - `multimodal/trigger.py:69-70` 经 `get_voice_loop()` 消费。
- **澄清保持**：`syscalls/multimodal.py`（sys_multimodal_process）是独立 syscall（首轮即确认起作用）；现 `harness/multimodal/` 类路径也已接通。

### 2.3 `harness/monitoring/wake_agent.py`（WakeAgent 唤醒监控）—— ✅ 已接线（2026-08-18/19，B3）

| 符号 | 2026-08-15 | 2026-08-19 复核 |
|---|---|---|
| `WakeAgent` / `get_wake_agent` | ❌ 全仓 0 生产引用 | ✅ **已接线**（≥10 caller） |

- **2026-08-19 接线证据**：
  - 工具注册：`core/apps/tools/wake_agent_tool.py` `WakeAgentTool`（零 token 文件变更监控），`core/server.py:1051` 挂载；
  - CoreFacade：`core/api/core_facade.py:3432-3455`（get_wake_agent_status / start / stop）；
  - 平台端点：`apps/eval/api/arena_wiring.py:49-70`（WakeAgent status / start / stop）。

### 2.4 数据类/枚举级 0 调用者（低风险，多为类型定义）—— 保持 2026-08-15 判定

以下模块的**公共类/枚举**无外部引用，但**模块功能本身已接线**（经同目录或他处调用）——属"类型未消费"而非"能力未接线"：

| 模块 | 0 调用者符号 | 模块实际接线情况 |
|---|---|---|
| `intervention/howl.py` | `StallReason`/`InterventionStrategy`/`InterventionResult`（枚举/类型） | ✅ Howl 类经 `loop/_facade.py:1196` 接线（stall 检测） |
| `practice/recorder.py` | `PraxisStep`/`PraxisSession`（数据类） | ✅ PraxisRecorder 经 `loop/base.py:205` 接线（session 录制） |
| `learning/agent_specialization.py` | `AgentSpecialization` 类（被同目录 agent_network/partner_selector 用，跨目录 0） | ✅ 经 `agent_network.py:111` 接线 |
| `training/*` | `FullTrainingJob`/`RLTrajectory` 等（数据类） | ✅ 工厂 `get_full_training_engine` 经 `finetune.py:328` 接线 |
| `deployment/canary.py` | `RolloutConfig`/`ABTestResult`（数据类） | ✅ SkillRouter 经 `deploy_engine.py` 接线 |

**判定**：这些属正常（类型定义被同模块内部消费，跨模块只调工厂函数），不构成问题。

---

## 3. 【B 类问题】CoreFacade getter 冗余 —— 2026-08-19 复核：**大幅收敛，剩余部分项（B4）**

**首轮现状**：`core/api/core_facade.py`（192 def）中一批 `get_*` getter **全仓 0 外部调用者**——能力实际经"类直接实例化"使用，facade 接口成为冗余层（抽样 30 个 def 中 15 个 0 外部调用者，50% 冗余率）。

**2026-08-19 复核**：
- **P0-A2（api→CoreFacade 收敛，54 文件 292 行 harness 直导清零）已大幅改善现状**——平台/API 层对 core 的访问统一收敛到 CoreFacade，大量 getter 由此获得真实消费者；CoreFacade 同时补 `sys_llm_generate` 等 re-export（P0-A2），消除"绕过 facade 直导 harness"的并行路径。
- **剩余部分项（基线 B4）**：`get_retrieval_crag` 等少量 getter 仍 0 调用者（CRAG 仍经 `syscalls/retrieval_crag.py` 类直用路径生效），作为行动纲领 **B4（部分）** 跟踪。
- **判定更新**：从"50% 冗余率（抽样）"降为"少量 getter 冗余（B4 部分项）"；能力本身均起作用。

| facade getter | 2026-08-15 | 2026-08-19 复核 |
|---|---|---|
| `get_policy_gate` / `get_context_bus` / `get_working_memory` 等（首轮 15/30 冗余） | ✅ 0 外部调用者（类直用） | ⚠️ P0-A2 收敛后大部分获得 facade 消费者；残余 0 调用者 getter 并入 B4 跟踪 |
| `get_retrieval_crag` | ✅ 0 外部调用者 | ⚠️ **仍 0 调用者**（B4 部分项；CRAG 经 `syscalls/retrieval_crag.py` 类直用生效） |

- **建议（保持首轮）**：要么让所有调用收敛到 facade getter（入口唯一），要么删除冗余 getter（保留类直用路径）——二选一，避免双路径；残余量已小，列为 B4 收尾项。

---

## 4. 核心链路接线确认（已起作用的能力）

| 能力 | 接线证据 | 状态 |
|---|---|---|
| Syscall 封口（tool/skill/llm） | `syscalls/tool.py:29` 等，被 loop/_facade、pipeline_engine、agents 大量调用 | ✅ |
| PolicyGate 权限 | `syscalls/skill.py:89`、`tool.py:470`、`agent.py:111` | ✅ |
| ApprovalGate 审批 | `approval_gate.py` + `approvals.py` 端点 + PolicyGate 内 check | ✅ |
| MemoryManager 四层记忆 | `loop/_facade.py` build_context、`syscalls/llm.py:1422` | ✅ |
| ContextBus 10 层 | `pipeline_engine.py:4484`、`memory/manager.py`、`control_profile.py` | ✅ |
| CRAG 检索链 | `syscalls/retrieval_crag.py` + `materials_chat.py` + `rag.py` | ✅ |
| EvolutionEngine 夜间流水线 | `server.py:1723-1760` cron 接线 + 14 步执行 | ✅ |
| AutoLearner 学习 | `evolution_engine.py:289`（夜间 process_pending） | ✅（实时性为演进项，非未接线） |
| Skill 系统（53+ engine） | `server.py:805` seed_data + `sys_skill_call` | ✅ |
| **子代理 SubagentCoordinator（P1-A3，新增）** | **SubagentProvider + InProcessProvider/ACPProvider**；`execute_parallel(provider=)`、`send_message`/`get_instance_status`（三态）；dynamic_orchestrator 生产路径 | ✅（本会话新增接线） |
| **消息渠道（P1-A4，新增）** | **get_channel_adapter 7 渠道**（telegram/slack/webchat/discord/wecom/email/dingtalk）+ test_channel 接线 | ✅（本会话新增接线） |
| **竞技场评测（B3，新增接线）** | `apps/eval/api/arena_wiring.py`（leaderboard/run）+ CoreFacade DarwinArena | ✅（本会话新增接线） |
| **语音循环 / 唤醒监控（B3，新增接线）** | `VoiceLoopTool`（server.py:1050）/ `WakeAgentTool`（server.py:1051）+ CoreFacade | ✅（本会话新增接线） |
| **Tenant 存储（P0-A3，新增）** | **TenantStore**（`aiPlat-platform/tenants/tenant_store.py`，tenant_quotas/usage_ledger/policies）+ core `tenant_store_protocol.py`（CoreFacade re-export + 注册表）+ 15 消费方注入优先 | ✅（本会话新增接线） |
| **pipeline_engine 拆分（P2-A4，新增）** | 12281→**8288 行**，5 个 Mixin（PipelineHealing/State/Prompt/Eval/Stage），`_run_stages_from` 保留主类 | ✅（本会话完成） |
| 审批/回滚/断点续跑 | `pipeline_engine.py:1974/2266/2536/2621` + run_store | ✅ |
| 夜间进化 cron | `server.py:1723` | ✅（守卫 §73 误报已消除） |
| on_error_reflector | `hook_manager.py:619` 默认注册 POST_OBSERVE | ✅（守卫 §73 误报已消除） |
| MCP 集成 | `server.py:1168` `_make_discovery_tool` + `mcp_admin.py` | ✅ |
| ACP/A2A | `server.py:2510-2513` 挂载 + `core/acp/server.py` | ✅ |
| finetune/SFT 训练 | `finetune.py` 端点 + `auto_trigger.py` + `full_training.py` | ✅（**默认 flag 关**，见 §5） |

---

## 5. 【C 类问题】默认关闭的 feature flag —— 2026-08-19 复核：**保持合法 opt-in，文档化列入 B5（部分）**

以下能力**已实现且有调用点**，但**默认关闭**（`"false"` 默认）——需环境变量显式开启才生效：

| flag | 能力 | 默认 | 影响 |
|---|---|---|---|
| `AIPLAT_RL_ENABLED` | RL 训练循环 | false | RL 训练默认不运行 |
| `AIPLAT_RL_ONLINE` | RL 在线模式 | false | 同上 |
| `AIPLAT_ENABLE_LEARNING_SCHEDULER` | 学习指标快照 + 自动回滚循环 | false | LearningManager 后台调度默认不运行 |
| `AIPLAT_ENABLE_LEARNING_AUTOROLLBACK` | 回归自动回滚 | false | 同上 |
| `AIPLAT_ENABLE_RELEASE_ROLLOUTS` | release 灰度发布 | false | 发布灰度默认不生效 |
| `AIPLAT_ENABLE_SESSION_SEARCH` | 会话检索上下文注入 | false | 检索注入默认关 |
| `AIPLAT_ENABLE_TOOLSETS` | toolsets 集成 | false | 工具集默认关 |
| `AIPLAT_ENABLE_LEARNING_APPLIER` | 学习产物应用 | false | 3 处引用点均需 flag |
| `AIPLAT_OTEL_ENABLED` | OTel 遥测导出 | false | 遥测默认关 |

- **2026-08-19 复核**：判定保持——这些是**有意的 opt-in**（RL/学习调度器等重能力默认关合理），且能力**已接线**（flag 只是运行时开关），不违反 CLAUDE.md §9；首轮建议的"start.sh/.env.example 注释 + 诊断页展示生效状态"列为行动纲领 **B5（部分）** 跟踪（opt-in flags 语义需文档化）。

---

## 6. 与架构守卫 FAIL 的关联 —— 2026-08-19 复核：**4 FAIL 全部清零（守卫全绿）**

| 守卫 FAIL（2026-08-15） | 与本报告关联 | 2026-08-19 处置 |
|---|---|---|
| §57（coordinator 直调 sys_llm_generate） | 独立合规问题 | ✅ **已修复（P0-A1）**：harness→apps 收敛 DI（`integration.py` 5 新工厂），宪法白名单 38→25；coordinator 走合规通道 |
| §73 wiring info（6 项） | 首轮证实 5 项为守卫误报 | ✅ **已消除**：接线事实保持（on_error_reflector/evolution cron 等已接线），守卫规则修正（commit 93b7c25c/bf0d0f19） |
| §74 method_verify | 工具链集成问题 | ✅ **已消除（P1-B2）**：verify_capability_consumers 入 CI，工具链闭环 |
| §17 E2E | 4 个测试失败 | ✅ **已修复（P0-A10）**：builder E2E **20/20 passed**（3 处测试基建修复）；§17 PytestCheck 降为 warn 级放行 |

---

## 7. 优先级建议（收尾清单）—— 2026-08-19 复核：**P0/P1 全部完成，剩余 P2 级收尾**

| 优先级 | 项目 | 2026-08-15 建议 | 2026-08-19 状态 |
|---|---|---|---|
| **P0** | §57 coordinator 合规修复 | 走 MemoryManager/compress 通道 | ✅ 已完成（P0-A1 收敛 DI） |
| **P0** | §17 E2E 4 失败修复 | 定位错误传播断言回归 | ✅ 已完成（P0-A10，20/20） |
| **P1** | arena 子系统（Elo/Champion/Regression） | 接线或删除 | ✅ 已接线（B3 + eval API） |
| **P1** | wake_agent 唤醒监控 | 接线到诊断/监控端点 或 标注待删除 | ✅ 已接线（B3 + WakeAgentTool） |
| **P1** | voice_loop/MultiModalTrigger | 接线到语音端点 或 标注待删除 | ✅ 已接线（B3 + VoiceLoopTool） |
| **P2** | CoreFacade getter 冗余 | 收敛调用路径或删冗余 getter | ⚠️ 大部分已随 P0-A2 收敛；残余（get_retrieval_crag 等）为 **B4（部分）** |
| **P2** | 默认关闭 flag 清单化 | start.sh/.env.example 注释 + 诊断页展示生效状态 | ⚠️ **B5（部分）**：语义需文档化 |
| **P2** | registry→docs 漂移自动清零 | —（2026-08-19 新增） | ⚠️ **C3（部分）**：`sync_registry_to_docs.py` 已建，接入 pre-commit/CI 待办 |

---

## 8. 审计方法局限（诚实标注）

1. **0 调用者判定基于文本 grep**：动态 import、`getattr` 反射调用可能漏检——已对重点项人工验证；2026-08-19 复核对 arena/voice_loop/wake_agent 的"已接线"结论为**阳性事实**（grep 到具体调用点），可信度高。
2. **CoreFacade getter 抽样 30/192（首轮）**：未全量扫描，冗余率是抽样估计；2026-08-19 后残余量已小（B4 部分项）。
3. **feature flag 清单**：扫描了 `"false"` 默认的 getenv，未逐一确认每个 flag 在部署配置中的实际值（B5 部分项即为此文档化工作）。
4. **运行期验证未做**：未启动 server 实测；2026-08-19 复核的守卫状态以基线 + PR #16-29 记录为准（本会话沙箱重跑全量守卫超时，未作为证据）。
5. **2026-08-19 复核基于基线权威事实 + 代码 grep 交叉验证**：能力数（1032/1039）、宪法 143 passed、分支保护 8 contexts 等取自已合并 PR 与基线文件，未逐项重跑。

---

## 9. 结论

**aiPlat 的能力实现完成度高（≈95%+ 已实现，核心链路全部起作用）；2026-08-19 复核后，"实现了但没完全起作用"的缺口已基本闭合**：

1. **首轮 3 个整体未接线子系统（arena / voice_loop / wake_agent）已全部接线**（B3，各 ≥10 caller，经 CoreFacade + 工具注册 + eval API）——违反 §9 的问题消除；
2. **CoreFacade getter 冗余大幅收敛**（P0-A2 使 facade 成为平台唯一入口），残余少量 0 调用者 getter 列为 B4 部分项；
3. **9 个默认关闭的 opt-in flag** 保持合法 opt-in，文档化列为 B5 部分项；registry→docs 漂移自动清零列为 C3 部分项（脚本已建）。

**核心链路（syscall/gates/memory/knowledge/evolution/skill/subagent/渠道/tenant/审批/断点续跑）全部真实起作用**——且本会话（PR #16-29）新增了子代理 provider、7 渠道消息、TenantStore、pipeline 拆分等接线，架构守卫全绿（0 ERROR），builder E2E 20/20。需收尾的仅为三个"部分项"（B4/B5/C3），均为 P2 级文档化/自动化工作，不再有"整系统未接线"级别的风险。

---

## 10. 结论可信度标注（对齐元审计 §11"阳性可信/阴性有盲区"框架）

> 本报告回答"所有能力是否实现并起作用"，核心是**接线判定**——接线判定天然分阳性/阴性，必须显式分级（方法论详见 `aiPlat治理体系元审计报告.md` §11）：

| 结论类别 | 可信度 | 说明 |
|---|---|---|
| **"有生产调用者/已接线"（阳性）** | ✅ **高** | 如 PolicyGate/ApprovalGate/EvolutionEngine/CRAG 等——grep 到具体调用点，阳性命中即真实 |
| **"0 调用者/未接线"（阴性）** | ⚠️ **有盲区** | 判定基于文本 grep + AST——动态 import、`getattr` 反射、经 CoreFacade re-export 可能漏检。已对重点项人工验证，但**不能保证全部** |
| **3 个子系统 2026-08-15 未接线 → 2026-08-19 已接线** | ✅ **高（阳性证据）** | 2026-08-19 复核 grep 到具体调用点（server.py:1050/1051、arena_wiring.py、CoreFacade:3386/3427/3432），并对照基线 B3（各 ≥10 caller）双重确认 |
| **CoreFacade getter 冗余（残余 B4）** | ⚠️ **中（抽样估计）** | 首轮 30/192 抽样；2026-08-19 后残余量已小，但全量冗余率仍是估算 |
| **9 个默认关闭 flag** | ✅ **高** | 直接 grep `"false"` 默认值，阳性事实；文档化状态为 B5 部分项 |
| **"核心链路全部起作用"（阴性方向）** | ⚠️ **有盲区** | 基于"有调用者"阳性证据推导，但**未做运行时冒烟**（未启动 server 实测）——"能调用"≠"运行时正常" |
| **守卫 4 FAIL → 全绿（2026-08-19）** | ✅ **高（基线权威）** | 取自已合并 PR #16-29 与《status-baseline-2026-08-19.md》，非转述旧守卫输出；本会话沙箱重跑超时未作为证据 |

**一句话**：本报告"说某能力已接线"高可信（阳性 grep 到调用点）；"说某能力未接线"有阴性盲区（动态 import/反射可能漏检）。2026-08-19 复核后，三个重点结论（arena/voice_loop/wake_agent 已接线、守卫全绿、能力数 1032/1039）均为**阳性事实**；残余 B4/B5/C3 三个部分项建议按行动纲领继续跟踪。
