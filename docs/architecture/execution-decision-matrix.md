# 执行决策矩阵

> **一句话**：帮你选「这件事该用程序、LLM、技能、Agent，还是流水线」——先按场景判断，细节与代码证据在文末附录。  
> **状态**：Living Spec（与实现同步；冲突时以代码为准）· **v1.4** · 2026-10-11  
> **互补文档**：[产物怎么验收](execution-quality-gates.md) · [能力剖面细节](capability-profile.md) · [知识 / Memory / CRAG](../knowledge-system.md) · [Agent 总览](../agent-system.md)（后端规则以本文为准）

---

## 1. 先记住五条

1. **能写死规则就别用模型**——权限、闸门、算术、已有 handler，都走程序。  
2. **加能力从便宜到贵**——改现有代码 → Skill/CLI → Tool → 插件 → MCP → 新内核接口。  
3. **行为靠配置字段，不靠「某个 Agent 名字」**——引擎里禁止按业务角色硬编码分支。  
4. **想钉死怎么跑，写「执行混合」或显式后端**——二者都不会被能力剖面降级。  
5. **工厂生成物尽量薄**——只选 Agent 类型 + 技能/工具；怎么跑交给引擎或团队配置（期望 profile 见 §8 E1）。

---

## 2. 我该选谁？（按需求）

| 你想做的事 | 首选 | 别这样做 |
|------------|------|----------|
| 「满足条件就拒绝 / 必须可审计」 | 程序规则、策略门 | 让模型当权限系统 |
| 稳定的读文件、调 API、算数 | Tool 或带代码的 Skill | 纯提示词假装已经执行成功 |
| 有固定业务步骤，但中间要模型填语义 | Skill（提示词或「模型规划 + 程序执行」） | 把长 SOP 塞进流水线配置里的 prompt |
| 多步探索、自己选工具、做错能改 | Agent（工具循环 / 先计划再执行） | 单次调用假装完成多步任务 |
| 固定多角色流水线（产品→架构→编码） | Workflow / Pipeline | Agent 随便拉其它 Agent、无门控 |
| 接外部 SaaS 工具集 | MCP（或薄一层 Tool） | 为核心路径新建内核接口 |
| 写代码并落到磁盘 | 编码闭环（沙箱 + 完成校验 + 审查）；优先 Agent 环 | 空回复直接落盘 |

**何时用模型、何时用程序：** 能规则化/可审计 → 程序；语义生成/多跳探索 → 模型；两者都要 → 混合或 Agent 循环。

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
**未知/拼写**：生产或 `AIPLAT_EXECUTION_TYPE_FAIL_CLOSED=1` → 硬失败；非生产默认 WARNING 后当 prompt（见 §7）。

### 组合矩阵（有 `skill_name` 时）

| Stage `execution_backend` | Skill `execution_type` | `handler.py` | **实际路径** |
|---------------------------|------------------------|:------------:|--------------|
| 任意（含 `llm`） | `handler` | 有 | **直接 `handler.py`**，不进 llm/agent 分支 |
| 任意 | `handler` | 无 | **失败**（不降级 LLM） |
| 任意（含 `llm`） | `hybrid` | 有 | **Stage：直接 `handler.py`**（路径卡 `path=hybrid`）；完整「LLM plan→handler」在 `sys_skill_call` → `Skill.execute` |
| 任意 | `hybrid` | 无 | **失败** |
| `llm` | `prompt` / 空→prompt | — | **`sys_llm_generate` + SOP**（不经 `Skill.execute` 主循环） |
| `agent` | `prompt` / 空→prompt | — | **StageRunner → ReAct/Plan 环**；环内可再 `sys_skill_call` |
| 任意 | **未知** | — | 生产硬失败；开发 soft→prompt 后再走上表 |

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

- 工厂：**只选** 对话 / react / rag + 技能工具；Skill 默认 prompt；**不要**乱写能力剖面/后端。  
- 钉死跑法：放**团队 YAML**（执行混合或 `execution_backend`）。工厂尚不能声明期望 profile → §8 E1。  
- 工作区 Execute：写文件类技能会注入编码闭环；`coding_closed_loop: false` 可关。  
- 编码落盘：Pipeline llm 路径有落盘前校验；优先 Agent 环做 peer-review。

| 评审问题 | 建议 |
|----------|------|
| 只要问答？ | 对话型 |
| 要工具 / 多步？ | react + 工具/技能；团队钉 `react_tools` |
| 主路径检索？ | rag |
| 要审完再完成？ | 不要赌 oneshot；用工具循环 |
| 要业务 handler？ | 工厂不生成 → 手写 Skill |

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
| 未知 `execution_type` | **非 production → soft（WARNING→prompt）**；**production → 硬失败** | CI/生产务必设 `AIPLAT_PROFILE=production` 或 `AIPLAT_EXECUTION_TYPE_FAIL_CLOSED=1` |
| `AIPLAT_EXECUTION_TYPE_FAIL_OPEN` | 关 | 紧急放行未知类型；**高风险**——须人工记录原因与时限（治理见 §8 E5，尚未自动化） |
| capability 降级 agent→llm | **不对显式 agent / 执行混合生效** | 见 §3 |

---

## 8. 还没做完的（勿当现状）

| 编号 | 想法 |
|------|------|
| E1 | 工厂生成可声明期望 `architecture_profile` / backend；conformance 校验意图与路径 |
| E2 | 生成物支持产出带 `handler.py` 的 Skill |
| E4 | CI 静态：prompt 宣称写文件、声明 handler 无文件、未知类型、跳级 MCP/Syscall |
| E5 | `FAIL_OPEN`：开启人/原因/过期自动关 + 告警 |

---

## 9. 实施清单

1. 能规则化？→ 程序 / 闸门 / Tool。  
2. 单次语义、无工具？→ prompt / oneshot。  
3. 多步工具？→ Agent + react_tools（或 plan / reflect）。  
4. 多角色流水线？→ Pipeline + handoff。  
5. 外部系统？→ MCP（先证明便宜档做不到）。  
6. 编码落盘？→ 闭环；优先 Agent。  
7. 生成物？→ 三类型 + prompt Skill；钉死放团队配置。

---

## 附录 A · 字段与环境变量

| 键 | 作用 |
|----|------|
| `architecture_profile` | 钉死执行混合（最强） |
| `execution_backend` | `llm` \| `agent`（写成 agent = 显式钉死） |
| `upgrade_policy` | `off` \| `signals` \| `aggressive` |
| `capability_profile` | `auto` 或显式等级 |
| `agent_type` / `execution_type` | 类工厂 / Skill 执行形态 |
| `meta_tool` / `done_verify` / `review_gate` / `uses_file_output` | 偏码与编码闭环 |
| `pipeline_mode` / `routing_mode` / 辩论·MoA | 编排 |
| `AIPLAT_EXECUTION_TYPE_FAIL_CLOSED` / `FAIL_OPEN` / `AIPLAT_PROFILE` | 未知类型策略 |
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
| v1.4 | 2026-10-11 | 完整 Stage×Skill 矩阵；显式 backend 不可 demote；路径卡补齐字段 + hybrid；设计模式映射；安全默认与 Memory/Eval 指针；回应组合/粒度/工厂/CI 缺口 |
| v1.3 | 2026-10-11 | 可读性改版（场景优先，证据进附录） |
| v1.2 | 2026-10-11 | E3 路径卡 |
| v1.1 | 2026-10-11 | 优先级链 + 未知类型硬失败 |
| v1.0 | 2026-10-11 | 首版 |
