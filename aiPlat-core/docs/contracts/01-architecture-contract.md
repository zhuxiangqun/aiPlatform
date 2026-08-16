# Architecture Contract（架构契约）

本文件定义 aiPlat 的架构“硬约束”。目标是防止实现随意演进导致：循环依赖、边界失守、治理失效、可观测断裂。

## 1. 分层与边界（MUST）

aiPlat 逻辑上分为：

1) **Kernel / Runtime（内核运行时）**  
负责：上下文传播、syscall 边界、可观测事件、资源/隔离抽象。

2) **Harness（执行框架）**  
负责：Loop（ReAct/Plan&Execute）、Agent/Tool/Skill 调度、context 管理、gates（policy/approval/resilience/trace）。

3) **Apps（业务组件）**  
负责：tools、skills、exec backends、gateway/channels、learning loop 等具体能力。

4) **Server/API（外部接口）**  
负责：HTTP 契约、鉴权、tenant 解析、将请求注入到 Harness。

### 1.1 依赖方向（MUST）

- `core/apps/*` **MUST NOT** 通过包级 `core.harness` 触发 Harness 的重型导入链路。  
  允许导入 **具体子模块**（例如 `core.harness.kernel.runtime`），但必须确保不会引发循环依赖。
- `core/harness/__init__.py` **MUST** 保持轻量（lazy export），不得在 import 时加载 execution/loop/tools 等重型模块。
- `core/server.py` **MAY** 依赖 apps/harness，但 apps/harness **MUST NOT** 反向依赖 server。

> 说明：这条约束用于避免“任意 import 都把系统启动一遍”，并降低循环依赖风险。

### 1.2 Layer Boundary Contract（MUST）

以下边界用于约束 `aiPlat-core` 内部各层职责，防止运行时内核、业务语义、会话编排、执行能力之间的边界失守。

#### Harness Contract

- `core/harness/*` **MUST** 提供统一执行运行时，包括 `run / event / wait / context / queue / registry / syscall` 等共性能力。  
- Harness **MUST NOT** 承载资料问答、视频问答、多资料比较、适用性分析等业务语义决策。  
- Harness **MUST** 解决“任务如何被执行”的问题，**MUST NOT** 解决“业务上本轮该如何回答”的问题。

#### Policy Contract

- Internal Policy / Service **MUST** 提供问题分析、检索路由、回答策略、会话级领域决策等通用能力。  
- Internal Policy / Service **SHOULD** 保持低副作用、可解释、可测试。  
- Internal Policy / Service **MUST NOT** 替代 Skill 承担底层执行细节。  
- `question_analysis / retrieval_policy / answer_strategy` 当前 **MUST** 视为 internal policy modules，而非普通 Skill。

#### Agent Contract

- Agent **MUST** 作为会话/任务编排器，负责上下文整合、策略调用、能力调度、结果写回。  
- Agent **MUST NOT** 直接实现复杂底层检索、索引、切片、存储等执行细节。  
- Agent **SHOULD** 优先通过 Internal Policy 做高层判断，通过 Skill 执行具体能力。

#### Skill Contract

- Skill **MUST** 提供单一职责、明确输入输出、可复用的执行能力。  
- Skill **MUST NOT** 承担系统级高层路由与策略决策。  
- 若某能力本质上属于问题分析、路由规划、回答策略，而非独立执行单元，则 **SHOULD NOT** 优先 Skill 化。

#### API Facade Contract

- `core/api/routers/*` **MUST** 保持薄入口，负责请求校验、身份透传、执行请求封装。  
- API Facade **MUST NOT** 内嵌核心领域策略与业务语义决策。  
- 领域策略、资料问答路由、回答规划 **MUST** 下沉到 Apps/Services/Policy 层。

## 2. 契约优先（MUST）

当出现以下冲突时，处理顺序必须是：
1) 更新实现以符合契约；或
2) 变更契约（需要明确理由 + 风险），并补齐验收用例。

## 3. 扩展点与插件化（SHOULD）

新增能力应优先以“注册/声明”的方式接入，而不是在核心路径硬编码：
- ToolRegistry：工具注册/查询/动态发现
- Skill registry / Skill packs：技能包发布与安装
- ExecDriver registry：执行后端扩展（local/docker/ssh…）
- Gateway adapters/connectors：渠道适配与交付

## 4. 错误与返回结构（MUST）

对外 API 与 syscall 边界处的错误 **MUST** 使用“结构化错误封装”，至少包含：
- `ok`（成功布尔）
- `error.code`（稳定错误码）
- `error.message`（可读信息，避免泄漏敏感内容）
- `trace_id/run_id`（若可用）

## 5. 变更控制与 ADR（SHOULD）

对下列变更 **SHOULD** 写 ADR 或至少在 PR 描述中给出“决策记录”：
- syscall/gate 行为变化
- prompt 组装逻辑变化（stable/ephemeral、cache key、compaction）
- tool/skill 权限模型变化
- exec backend 引入/删除
- gateway/多入口链路变化

推荐将 ADR 放在：
- `docs/architecture/` 或 `docs/design/` 对应子目录

---

## 附录 A：2026-08 P0-P1 架构变更记录

本附录记录 P0-P1 大规模改造期间对 core 边界的变更（满足 PR binding check 的契约更新要求）：

- **宪法合规（P0-A1~A10）**：harness→apps 反向依赖收白名单（`integration.py`）；api→engine 直导收敛 CoreFacade；platform LLM 推理收敛门面；`doc_compressor.llm_summarize` 作为 LLM 摘要唯一通道（§57 上下文组装合规）。
- **facade 收敛（P0-B4）**：删除 30 个 0 调用者 CoreFacade getter（类直用路径保留，§10 入口唯一性）。
- **学习闭环（P1-A1/A2）**：`learn_nudge_hook`（POST_OBSERVE 实时学习触发）+ `learning/skill_curator`（委托 harness/knowledge 实现，不违反 harness→apps 边界）。
- **子代理 provider（P1-A3）**：`SubagentProvider` 抽象 + in_process/acp 双 provider（对齐 DSH 契约）。
- **syscall 边界**：CrossValidationGate 经 CoreFacade + diagnostics 端点接线（条件激活 stub 获得生产调用者）。

**契约不变项**：单向依赖链（app→platform→core→infra）、syscall 三通道唯一性（sys_llm_generate/sys_tool_call/sys_skill_call）、Prompt Cache 稳定性约束均未改变。

## 附录 B：2026-08 P2 架构变更记录（Phase 5）

- **goal judge（P2-A6）**：`event_loop._judge_goal_condition` 每轮评估 goal 触发达成度（内置条件 + judge_expr），未达成在 `iterations_left` 预算内续跑（每次续跑独立 run）；LLM judge 预留未启用。
- **no-agent script 模式（P2-A7）**：cron 触发 `params.mode="script"` 直接执行 bash/sh/python3（零 LLM），fail-closed 入口白名单；无 run 记录，经 scheduler 日志观测。
- **CodeGraph gitignore 感知（P2-B5）**：`should_skip` 增加 `git check-ignore`，未跟踪但被忽略的文件不入图。

**契约不变项**：syscall 三通道唯一性、单向依赖链、Prompt Cache 稳定性约束均未改变；script 模式不产生 syscall 事件（无 LLM 通道）。

- **事件源双写（P2-A1）**：`PipelineRunStore` 新增 `pipeline_run_events` append-only 事件日志（阶段/phase/hitl 事件），引擎状态回调双写；run 状态快照保留（向后兼容），事件供回放/审计/UI 时间线。
