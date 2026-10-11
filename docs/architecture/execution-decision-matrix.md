# 执行决策矩阵

> **一句话**：帮你选「这件事该用程序、LLM、技能、Agent，还是流水线」——先按场景判断，细节与代码证据在文末附录。  
> **状态**：Living Spec（与实现同步；冲突时以代码为准）· **v1.7** · 2026-10-12  
> **互补文档**：[产物怎么验收](execution-quality-gates.md) · [能力剖面细节](capability-profile.md) · [知识 / Memory / CRAG](../knowledge-system.md) · [Agent 总览](../agent-system.md)（后端规则以本文为准）

---

## 1. 先记住五条

1. **能写死规则就别用模型**——权限、闸门、算术、已有 handler，都走程序。  
2. **加能力从便宜到贵**——改现有代码 → Skill/CLI → Tool → 插件 → MCP → 新内核接口。  
3. **行为靠配置字段，不靠「某个 Agent 名字」**——引擎里禁止按业务角色硬编码分支。  
4. **想钉死怎么跑，写「执行混合」或显式后端**——二者都不会被能力剖面降级。  
5. **工厂生成物尽量薄，但可声明期望跑法**——选 Agent 类型 + 技能/工具；推荐写 `architecture_profile`（E1）；团队 YAML 仍可覆盖。

---

## 2. 我该选谁？（按需求）

| 你想做的事 | 首选 | 别这样做 |
|------------|------|----------|
| 「满足条件就拒绝 / 必须可审计」 | **程序规则 / PolicyGate** | 让模型当权限系统 |
| 原子能力：读文件、调 API、算数（无业务 SOP） | **Tool**（可配 `meta_tool` 强制 code） | 纯提示词假装已执行 |
| 固定业务步骤 + 确定性副作用 | **handler Skill**（`handler.py`） | 用 prompt 假装写盘/调 API 成功 |
| 固定业务步骤，中间要模型填语义 | **prompt / hybrid Skill** | 把长 SOP 塞进流水线 `config.prompt` |
| 多步探索、自己选工具、做错能改 | **Agent 环**（`react_tools` 等） | 单次调用假装完成多步 |
| 固定多角色流水线 | **Workflow 编排**多 stage（stage 内仍是 Agent 或 Skill） | Agent 无门控互调；把 Workflow 当成「不要 Agent」 |
| 外部多工具 / 第三方维护的工具集 | **MCP**（见下方准入） | 为核心高频路径新建内核 Syscall |
| 写代码并落到磁盘 | 编码闭环；优先 Agent 环 | 空回复直接落盘 |

### 2.1 LLM vs 程序（硬规则）

| 条件 | 路径 |
|------|------|
| 结果必须可复现、可审计、可规则化 | **程序**（PolicyGate / handler / Tool） |
| 需理解自然语言、开放生成、语义填充 | **模型**（prompt / oneshot） |
| **单次**「模型出计划 → 程序执行」 | **`hybrid` Skill**（syscall `Skill.execute`） |
| **多轮**工具调用、观察结果、自我纠正 | **`agent` 循环**（`architecture_profile=react_tools` 等） |
| 算术 / 日期 / 结构化解析 / 转义规范化 | **禁止纯 LLM 心算** → Tool 或 `meta_tool` 强制走 code（见 §2.3） |

> 「两者都要」**不是**随便选 hybrid 或 Agent：单次计划+执行用 hybrid；需要多轮反馈用 Agent。

### 2.2 Tool vs handler Skill vs 程序

| 形态 | 何时选 |
|------|--------|
| **程序 / PolicyGate** | 权限、闸门、配额、合规——全局横切，不进业务 SOP |
| **Tool** | 原子、无业务步骤、多 Agent 可复用（`sys_tool_call`） |
| **handler Skill** | 有业务步骤/SOP、可复用、副作用可声明（`effects`），且执行是确定性代码 |
| **prompt Skill** | 步骤在 SOP 里，但中间判断必须靠模型 |

### 2.3 meta-tool（该算就算）

算术、日期差、JSON/CSV 解析、路径规范化等**确定性变换**不得交给模型「心算」。Stage/Agent 可声明：

- `meta_tool.enabled` / `auto_bind` — 优先绑定 code 类元工具  
- `meta_tool.force` — 强制走 code（逃逸舱口）  

落点：`PipelineStageConfig.meta_tool` → loop 上下文 `_prefer_code_meta_tool` / `_force_code_meta_tool`。

### 2.4 Workflow 与 Agent（不是二选一）

**Workflow / Pipeline = 编排壳**：决定 stage 顺序、handoff、HITL。  
**每个 stage 内部**仍按 §3/§4 选 `execution_backend` + Skill：可以是 Agent 环，也可以是 handler / oneshot。  
禁止把「用了 Pipeline」理解成「不许用 Agent」。

### 2.5 MCP 准入（硬标准）

| 选 MCP | 选薄 Tool |
|--------|-----------|
| 多工具包、外部维护、协议边界清晰 | 单原子操作 |
| **非**核心热路径（描述 token 贵） | 内部核心高频（宜进 ToolRegistry） |
| 已证明阶梯 1–4 做不到（见根 CLAUDE.md §20） | 扩展已有代码 / CLI / Skill 即可 |

新 MCP / 新 Syscall 合入须过 `scripts/check_cost_ladder.py`（E4）。

---

## 3. 「架构」三层（别混称）

### 层 A — 这一步怎么跑？（执行混合）

| 名字 | 人话 | 适合 |
|------|------|------|
| **oneshot** | 问一次模型，出结果，不拿工具 | 单次写文档、出结构 |
| **react_tools** | 边想边用工具/技能，可多轮 | 查资料、改文件、多步任务 |
| **plan_execute** | 先列计划再执行 | 步骤多、要可控分解 |
| **reflect_loop** | 做完再反思一轮 | 质量敏感、愿意多花一轮 |

### 层 B — Agent 是哪一类？

标准类型 **6** 种。工厂生成时通常只选三者：**对话 / react / rag**。

### 层 C — 能力给多少？

见 [capability-profile.md](capability-profile.md)。可注入能力标志；**不得**压过显式钉死（见下）。

### 谁说了算？（优先级 · 已统一）

```
显式「执行混合」architecture_profile
  > 显式 execution_backend（schema 默认是 llm，写成 agent 即钉死）
  > 能力剖面的其它注入（工具/安全标志等）
  > schema 默认：单次模型
```

**规则（代码已对齐）**：`architecture_profile` **或** `execution_backend=agent` 均不可被 capability 降成单次模型。只有未来「推断出来的 agent 后端」才允许降级；当前 Stage 上的 `agent` 一律视为钉死。

编排级（辩论 / MoA / 多角色团队）是整条流水线组织方式，不是单个 Agent 的执行混合。

---

## 4. Skill 类型 + Stage×Skill 完整组合矩阵

### Skill 怎么执行

| 类型 | 人话 |
|------|------|
| **handler** | 跑同目录真实代码；没有文件就失败 |
| **hybrid** | **Syscall `Skill.execute`**：模型出计划再跑 handler。**Pipeline Stage**：与 handler 同支，直接跑 `handler.py`（不先 `sys_llm_generate`） |
| **prompt** | 模型按 SOP 推理 |

字段空：有 `handler.py` 倾向 handler，否则 prompt。  
**未知/拼写**：**默认硬失败**（fail closed）。开发软降级须显式 `AIPLAT_EXECUTION_TYPE_SOFT_DEV=1` 或 `FAIL_CLOSED=0`。紧急放行见 §7 E5。

### 组合矩阵（有 `skill_name` 时）

| Stage `execution_backend` | Skill `execution_type` | `handler.py` | **实际路径** |
|---------------------------|------------------------|:------------:|--------------|
| 任意（含 `llm`） | `handler` | 有 | **直接 `handler.py`**，不进 llm/agent 分支 |
| 任意 | `handler` | 无 | **失败**（不降级 LLM） |
| 任意（含 `llm`） | `hybrid` | 有 | **Stage：直接 `handler.py`**（路径卡 `path=hybrid`）；完整「LLM plan→handler」在 `sys_skill_call` → `Skill.execute` |
| 任意 | `hybrid` | 无 | **失败** |
| `llm` | `prompt` / 空→prompt | — | **`sys_llm_generate` + SOP**（不经 `Skill.execute` 主循环） |
| `agent` | `prompt` / 空→prompt | — | **StageRunner → ReAct/Plan 环**；环内可再 `sys_skill_call` |
| 任意 | **未知** | — | **默认硬失败**；仅 SOFT_DEV / 授权 FAIL_OPEN 才 soft→prompt |

要点：

1. **handler / hybrid 永远先于 backend**——写了 `execution_backend=llm` 也不能绕过代码 Skill。  
2. Stage 上的 hybrid **不是**「先 llm 再 handler」；要完整 hybrid 语义请走 syscall 调 Skill，或改 Stage 用 agent + 环内 skill_call。  
3. `prompt` + `llm`：**不**进 `Skill.execute` 的 handler 分支，是引擎 oneshot 读 SOP。

跑完记**路径卡**（不只 `path`）：

```text
decision = {
  architecture_profile, execution_backend, agent_type, capability_profile,
  execution_type, path / actual_path,   # handler | hybrid | agent | llm
  upgrade_policy, inferred_from,
  downgrade_reason, demote_skipped      # 为何降级 / 为何跳过降级
}
```

落点：`state["_execution_decision"]`、进度条、`decision_trace.execution`。

---

## 5. 工厂与工作区

- 工厂：选 对话 / react / rag + 技能工具；Skill **默认 prompt**。  
- **E1**：推荐在 AGENT.md 写 `architecture_profile`（conversational→oneshot，react→react_tools，rag→react_tools）。conformance 校验：值∈已知集且与 `agent_type` 兼容。团队 YAML 同名字段优先。  
- **E2**：仅当 PRD 要求确定性、无 LLM 副作用时，可声明 `execution_type: handler` 并同目录输出 `handler.py`（顶层 `execute`）；媒体目录名禁止自造 handler。注册时复制 sibling。  
- 工作区 Execute：写文件类技能会注入编码闭环；`coding_closed_loop: false` 可关。  
- 编码落盘：Pipeline llm 路径有落盘前校验；优先 Agent 环做 peer-review。

| 评审问题 | 建议 |
|----------|------|
| 只要问答？ | 对话型 + `oneshot` |
| 要工具 / 多步？ | react + `react_tools` |
| 主路径检索？ | rag + `react_tools` |
| 要审完再完成？ | 不要赌 oneshot；用工具循环 |
| 要确定性副作用？ | E2：`handler` + `handler.py`（非媒体目录名） |

---

## 6. 设计模式 → aiPlat 字段（官方映射）

| 模式 | 映射 | 状态 |
|------|------|:----:|
| Single Agent / 对话 | `agent_type=conversational` · oneshot 或轻环 | **原生** |
| Tool Use | `react_tools` + `required_tools` | **原生** |
| ReAct | `architecture_profile=react_tools` | **原生** |
| Plan-and-Execute | `architecture_profile=plan_execute` | **原生** |
| Reflection | `architecture_profile=reflect_loop` | **原生** |
| Self-Refine | `reflect_loop` + `done_verify` / 审查 skill | **组合** |
| Multi-Agent | 团队多 stage + handoff；或 `multi_agent` | **原生** |
| Router | `routing_mode`（llm 路由须 env opt-in） | **原生** |
| Debate | `debate_participants` | **原生** |
| MoA | `routing_mode=moa` / `moa_preset` | **原生** |
| Memory | MemoryManager / Team Brain / CRAG（横切，非 Stage 字段） | **组合** → [knowledge-system.md](../knowledge-system.md) |
| Loop Engineering | `done_verify` + `upgrade_policy` + 编码闭环 | **组合** |
| Tree-of-Thoughts (ToT) | 无一等字段；可用多 stage / 辩论近似 | **需扩展** |
| Graph-of-Thoughts (GoT) | 无一等字段 | **需扩展** |

Eval / 金标 / 值班板：见 Governance 与 apps/eval（本文不替代）；知识闭环见知识系统文档。

---

## 7. 默认安全与运维开关

| 行为 | 默认 | 说明 |
|------|------|------|
| 未知 `execution_type` | **硬失败（fail closed）** | 开发软降级：`AIPLAT_EXECUTION_TYPE_SOFT_DEV=1` 或 `FAIL_CLOSED=0` |
| `AIPLAT_EXECUTION_TYPE_FAIL_OPEN` | 关 | 须同时设 `REASON` + `BY` + `UNTIL`（未来时戳）才授权；缺任一或过期 → 仍 fail closed。启动写 sidecar + audit_log |
| capability 降级 agent→llm | **不对显式 agent / 执行混合生效** | 见 §3 |

---

## 8. 还没做完的（勿当现状）

| 编号 | 状态 | 说明 |
|------|:----:|------|
| E1 | **已做** | 工厂可写 `architecture_profile`；conformance 校验意图；team_planner 从 AGENT.md 回填（YAML 优先） |
| E2 | **已做** | 工厂可选 `execution_type: handler` + 同目录 `handler.py`（须顶层 `execute`）；conformance `check_handler_pairing`；注册时复制 sibling；媒体目录名禁止自造 handler |
| E4 | **已做** | `lint_engine_skills.py`（handler/未知类型/prompt 写文件）+ `check_cost_ladder.py`（新 Syscall/MCP 须 CAPABILITIES 或 `# ladder-ok`）；pre-commit + architecture_guard |
| E5 | **已做** | FAIL_OPEN 须 reason/by/until；过期自动无效；sidecar + 启动 audit_log |

---

## 9. 实施清单

1. 能规则化 / 权限闸门？→ 程序 / PolicyGate。  
2. 原子无 SOP？→ Tool；要算数/解析 → meta-tool / code。  
3. 单次语义、无工具？→ prompt / oneshot。  
4. 单次「计划→程序」？→ hybrid Skill；多轮纠正？→ Agent 环。  
5. 多角色？→ Pipeline **编排** stage（stage 内仍是 Agent/Skill）。  
6. 外部多工具？→ MCP（先证明 Tool/Skill 不够）；合入过 cost ladder。  
7. 编码落盘？→ 闭环；优先 Agent。  
8. 生成物？→ 三类型 + 推荐 `architecture_profile` + 默认 prompt；确定性副作用才用 E2 handler。

---

## 附录 A · 字段与环境变量

| 键 | 作用 |
|----|------|
| `architecture_profile` | 钉死执行混合（最强）；工厂 AGENT.md 可选（E1） |
| `execution_backend` | `llm` \| `agent`（写成 agent = 显式钉死） |
| `upgrade_policy` | `off` \| `signals` \| `aggressive` |
| `capability_profile` | `auto` 或显式等级 |
| `agent_type` / `execution_type` | 类工厂 / Skill 执行形态 |
| `meta_tool` / `done_verify` / `review_gate` / `uses_file_output` | 偏码与编码闭环 |
| `pipeline_mode` / `routing_mode` / 辩论·MoA | 编排 |
| `AIPLAT_EXECUTION_TYPE_FAIL_CLOSED` | `1` 强制硬失败；`0` 显式 soft（同 SOFT_DEV） |
| `AIPLAT_EXECUTION_TYPE_SOFT_DEV` | `1` 开发 soft→prompt（默认关） |
| `AIPLAT_EXECUTION_TYPE_FAIL_OPEN` + `_REASON` / `_BY` / `_UNTIL` | E5 紧急放行（三者齐全且未过期） |
| `AIPLAT_META_TOOL_*` / `AIPLAT_DONE_VERIFY*` / `AIPLAT_CODING_STAGE_*` | 元工具 / DONE / 编码默认 |
| `AIPLAT_DYNAMIC_ROUTER_ENABLED` | 模型动态路由 opt-in |
| `AIPLAT_EXECUTION_AUDIT` | Skill actual_mode 审计 |

---

## 附录 B · 代码证据

| 主题 | 符号 |
|------|------|
| 执行混合 | `schemas_builder.ARCHITECTURE_PROFILES` |
| Stage×Skill | `pipeline_engine._run_stage_skill` |
| Skill 执行 | `apps/skills/registry.Skill.execute` |
| 类型规范化 | `execution_type_policy.coerce_execution_type` |
| 默认 fail closed / E5 | `execution_type_fail_closed` · `fail_open_governance_status` · `record_fail_open_audit_async` |
| E4 CI | `scripts/lint_engine_skills.py` · `scripts/check_cost_ladder.py` |
| E2 handler Skill | `generated_conformance.check_handler_pairing` · `builder_project_service` 复制 handler.py · `agent_engineering` SOP |
| E1 工厂意图 | `generated_conformance._check_architecture_profile_intent` · `team_planner` 回填 · `agent_engineering` SOP |
| meta-tool | `PipelineStageConfig.meta_tool` · `meta_tool.apply_meta_tool_config` · `_prefer_code_meta_tool` / `_force_code_meta_tool` |
| 降级门闩 | `pipeline_stage._apply_capability_profile`（跳过显式 agent/profile） |
| 路径卡 | `build_execution_decision` · `_emit_execution_decision` |
| 工厂 SOP | `agent_engineering/SKILL.md` |
| 工作区闭环 | `inject_workspace_coding_defaults` |
| 成本阶梯 | 根 `CLAUDE.md` §20 |

**维护**：改上表路径时同 PR 更新本文；破坏性语义升 minor。  
**非目标**：不替代 PolicyGate 细则、合入物理闸门、CAPABILITIES 全表。

---

## 变更记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.7 | 2026-10-12 | 正文补齐：LLM/程序硬规则、hybrid vs Agent、Tool/handler/程序边界、meta-tool、Workflow 编排语义、MCP 准入（回应 v1.3 选型评审） |
| v1.6 | 2026-10-12 | E2 handler Skill 闭环标已做；E4 成本阶梯 `check_cost_ladder` 接入 pre-commit / architecture_guard |
| v1.5 | 2026-10-12 | 默认 fail closed；E1 工厂 architecture_profile + conformance；E4/E5 标已做；SOFT_DEV / FAIL_OPEN 治理 env |
| v1.4 | 2026-10-11 | 完整 Stage×Skill 矩阵；显式 backend 不可 demote；路径卡补齐字段 + hybrid；设计模式映射；安全默认与 Memory/Eval 指针 |
| v1.3 | 2026-10-11 | 可读性改版（场景优先，证据进附录） |
| v1.2 | 2026-10-11 | E3 路径卡 |
| v1.1 | 2026-10-11 | 优先级链 + 未知类型硬失败 |
| v1.0 | 2026-10-11 | 首版 |
