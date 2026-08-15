# aiPlat 实现完成度审计报告（能力是否实现 + 是否起作用）

> **审计目的**：回答"是不是所有能力都实现并且都起作用了"——**代码存在 ≠ 能力起作用**。本报告系统核查：声明能力是否实现（代码存在）+ 是否真正接线（有非测试生产调用者 / 经 CoreFacade / 经 HTTP 端点消费 / feature flag 未隐藏）。
> **审计方法**：AST 提取模块级公共符号 → 全仓生产代码 grep 调用者 → 人工交叉验证（排除工厂模式/动态 import/re-export 误报）→ 交叉验证 CoreFacade/HTTP 端点/前端页面消费。
> **审计时点**：2026-08-15。基线：architecture_guard 4 FAIL（§57/§73/§74/§17）+ capability_convergence 全 PASS + 死代码标记 0。

---

## 0. 总体结论

| 维度 | 结论 | 证据 |
|---|---|---|
| **实现完成度** | 高——声明能力绝大多数有代码实现 | capability_convergence 全 PASS；arch_guard 172 规则覆盖；死代码标记 0 |
| **接线完成度** | 中高——绝大多数核心能力已接线，但存在 **2 类未接线能力** | 见 §2（整体未接线子系统）+ §3（facade getter 冗余） |
| **核心链路** | 全部起作用（syscalls/gates/memory/knowledge/evolution 均有真实调用者） | 见 §4 |
| **主要风险** | ① 3 个子系统整体未接线（arena/multimodal voice_loop/wake_agent）；② 大量 CoreFacade getter 无人消费；③ 4 个默认关闭的 feature flag 掩盖未生效能力 | 见 §2/§3/§5 |

**一句话**：aiPlat 的能力"实现率"高（≈95%+ 已实现），但"生效率"非 100%——存在少数整体未接线的子系统（如 Elo 竞技场）和一批"实现了但没人调用的 facade 接口"，以及若干默认关闭的 opt-in 能力（RL 训练、学习调度器、release 灰度等，默认不运行）。

---

## 1. 审计基线（先确认工具链可信）

| 检查项 | 结果 | 证据 |
|---|---|---|
| architecture_guard.sh | **4 FAIL**（§57 NEW / §73 / §74 / §17） | `architecture_guard.py --json` ok:False |
| capability_convergence.py | **全 PASS**（所有能力汇聚到强制门禁） | 运行输出 [PASS] |
| 死代码标记（TODO wire/0 caller/待接线） | **0 处** | `grep -rn "TODO.*wire\|0 caller\|待接线" core/` 空 |
| caller_verify.sh | 已废弃（被 capability_convergence 替代） | 脚本头 DEPRECATED 声明 |

---

## 2. 【A 类问题】整体未接线的子系统（实现了，但 0 生产调用者）

### 2.1 `harness/arena/`（Elo 竞技场 + Champion Pipeline）——❌ 整体未接线

| 符号 | 文件 | 0 调用者确认 |
|---|---|---|
| `EloScorer` / `ChampionResult` / `ChampionPipeline` / `RegressionRunner` / `RegressionReport` / `BenchmarkTask` | `arena/arena.py`、`arena/regression.py` | ✅ 全仓 0 生产引用（无 import、无 CoreFacade、无 HTTP 端点、无前端页面） |

- **证据**：`grep -rn "harness.arena\|EloScorer" core/ platform/ --include='*.py' | grep -v tests` → 空；前端 `grep -rln "arena\|benchmark" frontend/src/` → 空。
- **影响**：CLAUDE.md/ROADMAP 声称的"竞技场对比评测"（Elo 评分、Champion 冠军流水线、回归基准）**当前未生效**——无任何入口能触发。
- **判定**：能力已实现但未接线（违反 CLAUDE.md §9"零调用者的模块必须标注待接线或待删除"）。

### 2.2 `harness/multimodal/voice_loop.py`（VoiceLoop 语音循环）——❌ 类未接线

| 符号 | 文件 | 确认 |
|---|---|---|
| `VoiceLoop` / `get_voice_loop` / `MultiModalTrigger` / `get_multimodal_trigger` / `GoalLoopBridge` / `get_goal_loop_bridge` | `multimodal/voice_loop.py`、`multimodal/trigger.py` | ✅ 0 生产引用 |

- **证据**：`grep -rn "VoiceLoop\|get_voice_loop" core/ --include='*.py' | grep -v "multimodal/"` → 空。
- **澄清**：`syscalls/multimodal.py`（sys_multimodal_process）是**独立的、已注册的 syscall**（起作用）；但 `harness/multimodal/` 下的 VoiceLoop/Trigger 类（语音循环、多模态触发）**未接线**。
- **判定**：类已实现未接线；syscall 层起作用。

### 2.3 `harness/monitoring/wake_agent.py`（WakeAgent 唤醒监控）——❌ 整体未接线

| 符号 | 确认 |
|---|---|
| `WakeAgent` / `get_wake_agent` | ✅ 全仓 0 生产引用（无 router、无 facade、无前端） |

- **证据**：`grep -rn "get_wake_agent\|WakeAgent" core/ platform/ app/ --include='*.py' | grep -v "monitoring/wake_agent.py"` → 空。
- **判定**：实现未接线。

### 2.4 数据类/枚举级 0 调用者（低风险，多为类型定义）

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

## 3. 【B 类问题】CoreFacade getter 冗余（facade 接口存在但无人消费）

**现状**：`core/api/core_facade.py`（192 def）中，一批 `get_*` getter **全仓 0 外部调用者**——能力实际经"类直接实例化"（如 `PolicyGate()`）或"其他路径"使用，facade 接口成为冗余层。

| facade getter | 0 外部调用者 | 能力实际使用路径 |
|---|---|---|
| `get_policy_gate` | ✅ | PolicyGate 被 syscalls 直接 `PolicyGate()` 实例化（`skill.py:89`）——facade getter 无人用 |
| `get_context_bus` | ✅ | ContextBus 类被 `pipeline_engine.py`/`memory/manager.py`/`control_profile.py` 直接使用——getter 无人用 |
| `get_retrieval_crag` | ✅ | CRAG 经 `syscalls/retrieval_crag.py` 直接调用 |
| `get_intent_analyzer` | ✅ | IntentAnalyzer 经 `orchestration/` 直接使用 |
| `get_working_memory` / `get_circuit_breaker` / `get_error_translator` / `get_graph_index` / `get_entity_resolver` / `get_class_mapper` / `get_state_machine` / `get_knowledge_validator` / `get_system_diagnostician` / `get_wiki_retriever` / `get_arch_guard_rules` | ✅（抽样确认） | 类均被各子系统直接使用 |

- **判定**：**能力起作用**（类被真实调用），但 **facade getter 接口冗余**（CLAUDE.md §10 API 入口唯一性未被遵守——存在"类直用 + facade 接口"双路径）。抽样 30 个 def 中 15 个 0 外部调用者（50% 冗余率）。
- **建议**：要么让所有调用收敛到 facade getter（入口唯一），要么删除冗余 getter（保留类直用路径）——二选一，避免双路径。

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
| AutoLearner 学习 | `evolution_engine.py:289`（夜间 process_pending） | ✅（但实时性缺，见 P1-1） |
| Skill 系统（53+ engine） | `server.py:805` seed_data + `sys_skill_call` | ✅ |
| 子代理 SubagentCoordinator | `multi_agent.py`/`parallel_executor.py` 调用 | ✅ |
| 审批/回滚/断点续跑 | `pipeline_engine.py:1974/2266/2536/2621` + run_store | ✅ |
| 夜间进化 cron | `server.py:1723` | ✅（守卫 §73 误报） |
| on_error_reflector | `hook_manager.py:619` 默认注册 POST_OBSERVE | ✅（守卫 §73 误报） |
| MCP 集成 | `server.py:1168` `_make_discovery_tool` + `mcp_admin.py` | ✅ |
| ACP/A2A | `server.py:2510-2513` 挂载 + `core/acp/server.py` | ✅ |
| finetune/SFT 训练 | `finetune.py` 端点 + `auto_trigger.py` + `full_training.py` | ✅（**默认 flag 关**，见 §5） |

---

## 5. 【C 类问题】默认关闭的 feature flag（能力实现了，默认不运行）

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

- **判定**：这些是**有意的 opt-in**（RL/学习调度器等重能力默认关合理），但需注意：CLAUDE.md §9 禁止"用 feature flag=false 掩盖未接线"——此处能力**已接线**（flag 只是运行时开关），不违反；但部署方必须知道"默认环境只生效 core 链路，RL/学习/灰度/遥测需显式开启"。
- **建议**：在 `start.sh`/`.env.example` 明确注释这些 flag 的用途，避免"以为在跑实际没跑"。

---

## 6. 与架构守卫 FAIL 的关联

本次审计发现与守卫 FAIL 直接相关项：

| 守卫 FAIL | 与本报告关联 | 性质 |
|---|---|---|
| §57（coordinator 直调 sys_llm_generate） | 独立合规问题（改 coordinator 走上下文压缩） | 真违规 |
| §73 wiring info（6 项） | **本报告证实 5 项为守卫误报**（on_error_reflector/evolution cron/implicit_feedback 等已接线），仅 `caller_verify_in_arch_guard` 真问题（工具链集成） | 误报为主 |
| §74 method_verify | 工具链集成问题（守卫自身未调 method_verify） | 工具链 |
| §17 E2E | 4 个测试失败（错误传播路径） | 真实测试失败 |

---

## 7. 优先级建议（接线的收尾清单）

| 优先级 | 项目 | 处置建议 | 工作量 |
|---|---|---|---|
| **P0** | §57 coordinator 合规修复 | 走 MemoryManager/compress 通道 | 0.5 天 |
| **P0** | §17 E2E 4 失败修复 | 定位错误传播断言回归 | 1 天 |
| **P1** | arena 子系统（Elo/Champion/Regression） | **接线或删除**：接入诊断中心"LLM 评测"页 或 标注待删除 | 1-2 天 |
| **P1** | wake_agent 唤醒监控 | 接线到诊断/监控端点 或 标注待删除 | 0.5 天 |
| **P1** | voice_loop/MultiModalTrigger | 接线到语音端点 或 标注待删除 | 1 天 |
| **P2** | CoreFacade getter 冗余（~50% 抽样） | 收敛调用路径或删冗余 getter（入口唯一性 §10） | 2-3 天 |
| **P2** | 默认关闭 flag 清单化 | start.sh/.env.example 注释 + 诊断页展示生效状态 | 0.5 天 |

---

## 8. 审计方法局限（诚实标注）

1. **0 调用者判定基于文本 grep**：动态 import（`from x import y` 的字符串形式）、`getattr` 反射调用可能漏检——已对重点项人工验证（Howl/PraxisRecorder/FullTraining/AgentSpecialization 均实际接线）。
2. **CoreFacade getter 抽样 30/192**：未全量扫描，冗余率是抽样估计（15/30=50%）。
3. **feature flag 清单**：扫描了 `"false"` 默认的 getenv，未逐一确认每个 flag 在部署配置中的实际值。
4. **运行期验证未做**：未启动 server 实测（沙箱只读 + 无 API key），"起作用"判定基于"有生产调用者 + 有接线点"，非运行时冒烟。

---

## 9. 结论

**aiPlat 的能力实现完成度高（≈95%+ 已实现，核心链路全部起作用）**，但存在三类"实现了但没完全起作用"的情况：

1. **3 个整体未接线子系统**：`arena`（Elo 竞技场）、`multimodal/voice_loop`（语音循环类）、`monitoring/wake_agent`（唤醒监控）——能力实现但无任何生产入口（违反 §9）。
2. **CoreFacade getter 冗余**（抽样 50% 无外部调用者）：能力经类直用路径生效，facade 接口成摆设（违反 §10 入口唯一性）。
3. **9 个默认关闭的 opt-in flag**：RL/学习调度/灰度/遥测等能力已接线但默认不运行（合法 opt-in，但部署需知晓）。

**核心链路（syscall/gates/memory/knowledge/evolution/skill/subagent/审批/断点续跑）全部真实起作用**——这正是 aiPlat"企业级"定位的支撑；需收尾的是边缘子系统的"接线或删除"决策与 facade 接口收敛。

---

## 10. 结论可信度标注（对齐元审计 §11"阳性可信/阴性有盲区"框架）

> 本报告回答"所有能力是否实现并起作用"，核心是**接线判定**——接线判定天然分阳性/阴性，必须显式分级（方法论详见 `aiPlat治理体系元审计报告.md` §11）：

| 结论类别 | 可信度 | 说明 |
|---|---|---|
| **"有生产调用者/已接线"（阳性）** | ✅ **高** | 如 PolicyGate/ApprovalGate/EvolutionEngine/CRAG 等——grep 到具体调用点（`syscalls/skill.py:89` 等），阳性命中即真实 |
| **"0 调用者/未接线"（阴性）** | ⚠️ **有盲区** | 判定基于文本 grep + AST——**动态 import（`from x import y` 字符串）、`getattr` 反射、经 CoreFacade re-export** 可能漏检。已对重点项人工验证（Howl/PraxisRecorder/FullTraining/AgentSpecialization 实际接线），但**不能保证全部** |
| **3 个整体未接线子系统**（arena/voice_loop/wake_agent） | ✅ **高（经双重确认）** | 全仓 grep 0 命中 + 无 CoreFacade + 无 HTTP 端点 + 无前端页面，四路交叉确认 |
| **CoreFacade getter 冗余（抽样 50%）** | ⚠️ **中（抽样估计）** | 抽样 30/192 def；"冗余"是阳性事实（0 外部调用者），但**全量冗余率是估算** |
| **9 个默认关闭 flag** | ✅ **高** | 直接 grep `"false"` 默认值，阳性事实 |
| **"核心链路全部起作用"（阴性方向）** | ⚠️ **有盲区** | 基于"有调用者"阳性证据推导，但**未做运行时冒烟**（未启动 server 实测）——"能调用"≠"运行时正常" |
| **与守卫 §73 关联的判断（5 项误报）** | ✅ **高（独立复核）** | 逐个 grep 确认实际已接线（hook_manager.py:619 等），非转述守卫输出 |

**一句话**：本报告"说某能力已接线"高可信（阳性 grep 到调用点）；"说某能力未接线"有阴性盲区（动态 import/反射可能漏检）——已对重点项人工验证，但 arena/voice_loop/wake_agent 三个经四路交叉确认的结论最可靠。**建议对"0 调用者"清单用 `grep -rn` 逐符号复核后再做"接线 or 删除"决策**（这正是报告 §7 的 P1 建议）。
