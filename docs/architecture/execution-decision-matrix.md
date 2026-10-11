# 执行决策矩阵（Execution Decision Matrix）

> **状态**：Living Spec（与代码同步；冲突时以代码为准）  
> **版本**：v1.0 · 2026-10-11  
> **权威代码锚点**：`schemas_builder.ARCHITECTURE_PROFILES` / `PipelineStageConfig` · `pipeline_engine._run_stage_skill` · `apps/skills/registry.Skill.execute` · `agent_types.yaml` · `agent_engineering/SKILL.md`  
> **相关文档**（互补，不替代本文）：  
> - [capability-profile.md](capability-profile.md) — 能力等级注入表  
> - [execution-quality-gates.md](execution-quality-gates.md) — **产物质量**门禁（做完后如何验收），非「选哪条执行路径」  
> - [agent-system.md](../agent-system.md) — Agent 生命周期总览（部分措辞已过时，以后端选择规则以本文为准）  
> - 根 `CLAUDE.md` §20 成本阶梯 · Core `CLAUDE.md` §5.24 扩展阶梯  

---

## 0. 如何迭代本文档

| 规则 | 说明 |
|------|------|
| **代码优先** | 本文描述「当前实现如何判定」。设计目标写在 §9「演进槽」；未接线目标不得写成现状 |
| **变更触发** | 修改下列任一者时，须同 PR 更新本文对应节：`ARCHITECTURE_PROFILES`、`execution_type` 分支、`_infer_profile_from_stage`、`create_agent` 路由、`agent_engineering` Step1 选型、成本阶梯条款 |
| **证据** | 每条判定须可 `grep` 到符号；表格「证据」列写 `path` + 符号名 |
| **版本** | 破坏性语义变更 → 升 minor（v1.x）；仅补例/澄清 → 文首日期即可 |
| **非目标** | 不替代 PolicyGate 细则、不替代合入物理闸门、不替代 CAPABILITIES 能力登记 |

---

## 1. 总原则（先记住这五条）

1. **能确定性就不要 LLM** — Hook / handler / Action handler / PolicyGate / done_verify / 物理闸门均属程序路径。  
2. **扩展按成本阶梯从低到高** — 扩展已有代码 → CLI+Skill → Tool → Plugin → MCP → 新 Syscall（根 CLAUDE.md §20）。  
3. **Stage 行为由配置字段驱动** — 禁止在引擎里 `if agent_id ==`；用 `architecture_profile` / `execution_backend` / `capability_profile` / `execution_type` 等。  
4. **`architecture_profile` 赢过裸 `execution_backend`** — 声明后覆盖 backend + agent_type，再套 coding defaults。  
5. **工厂生成物默认薄声明** — 工作区/工厂只选 `agent_type`（+ skills/tools）；`capability_profile` / `execution_backend` 交给引擎推断，除非团队 YAML 显式钉死。

---

## 2. LLM vs 程序：何时用谁

### 2.1 决策树（Skill 调用）

```
sys_skill_call
  → PolicyGate（程序：ALLOW/DENY/ASK）
  → Skill.execute 按 execution_type：
       handler      → handler.py.execute()          【程序，无 LLM】
       hybrid       → LLM 出 plan → handler 执行    【LLM + 程序】
       prompt       → LLM 按 SOP 推理              【LLM】
       （缺省/未知）→ 当 prompt，并记 WARNING
```

| `execution_type` | 是否调 LLM | 必要条件 | 证据 |
|------------------|------------|----------|------|
| `handler` | 否 | 同级 `handler.py` 存在且可加载，否则**硬失败**（禁止静默改走 LLM） | `apps/skills/registry.py` Skill.execute；CLAUDE.md §17 |
| `hybrid` | 是（规划）+ 否（执行） | handler + SOP | 同上 |
| `prompt`（别名 `llm`） | 是 | SOP 文本 | registry_loader 枚举 |
| `python_class` / `tool_wrapper` | 声明层存在 | 运行时主路径仍以 handler/hybrid/prompt 为主；新增须先接线再写进本文 | `registry_loader.py` enums |

**自动探测（注册时）**：有 `handler.py` → 倾向 `handler`（SOP 很复杂时可标 hybrid）；无 handler → `prompt`。声明 `handler` 但无文件 → 错误，不是降级 LLM。

### 2.2 决策树（Pipeline Stage）

```
apply_architecture_profile(stage)     # 可改 backend + agent_type
_apply_capability_profile(...)        # 注入能力；可能降级 agent→llm
if stage.skill_name:
  if debate_participants: 辩论编排
  elif execution_backend == "agent":
       StageRunner → ReActLoop / PlanExecuteLoop   【多步，可再调 LLM+工具】
  else:
       sys_llm_generate                             【oneshot LLM】
else:
  _exec_stage（node_type: llm|code|http|condition|…）
```

| 场景 | 选 LLM | 选程序 | 判定字段 |
|------|--------|--------|----------|
| 单次 SOP 出文/出结构 | ✅ oneshot | — | `execution_backend=llm` 或 `architecture_profile=oneshot` |
| 多步工具/技能闭环 | ✅ 在循环内 | 工具/handler 侧程序 | `execution_backend=agent` / `react_tools` |
| 算术/日期/解析/逃逸舱口 | 倾向否 | ✅ 优先 `code` 工具 | `meta_tool` + INTENT_PATTERNS |
| 权限/策略 | 否 | ✅ PolicyGate | syscall 入口唯一检查点 |
| DONE 是否成立 | 否 | ✅ `done_verify` | `_done_verify` / coding defaults |
| 合入膨胀/形态 | 否 | ✅ physical_merge_gates | CI/pre-commit |
| 本体 Action 执行 | 否（handler） | ✅ ActionRegistry | `contract.handler` |
| 检索召回（CRAG L0–L2） | 否 | ✅ cache/graph/FTS | `sys_crag_retrieve`；HyDE/L3+ 才 LLM |

### 2.3 Meta-tool：强制「该算就算」

| 意图标签 | 含义 | 默认动作 |
|----------|------|----------|
| `arithmetic` | 算术 | 提示/置顶 `code` / `code_execution` |
| `datetime` | 日期时间 | 同上 |
| `parse_transform` | 解析变换 | 同上 |
| `escape_hatch` | 逃逸舱口 | 同上 |

- Stage：`meta_tool: {enabled, auto_bind, force}`  
- Env：`AIPLAT_META_TOOL_CODE`（总开关）、`AIPLAT_META_TOOL_AUTO_BIND`（`auto` → 生产默认开）  
- 证据：`harness/execution/meta_tool.py`

### 2.4 一句话规则

> **判定是否「可写成确定性规则 / 可复现 / 可审计」——能 → 程序；需要语义理解、开放生成、多跳探索 → LLM；两者都要 → hybrid 或 agent 循环（LLM 决策 + 程序执行）。**

---

## 3. Agent / Skill / Tool / MCP / Workflow / 程序：选用矩阵

### 3.1 成本阶梯（强制，扩展能力时）

| 级 | 形态 | Token/运维成本 | 何时用 | 何时不用 |
|:--:|------|:--------------:|--------|----------|
| 1 | **扩展已有代码** | 0 | 变体、补丁、字段驱动即可 | — |
| 2 | **CLI + Skill（SOP）** | 低 | 配置/运维/可描述的步骤流程 | 需要严格 I/O 契约的高频原子操作 |
| 3 | **Service-gated Tool** | 中 | 结构化 I/O、可 `check_fn` 条件启用 | 未配置服务时不应占位 |
| 4 | **Plugin**（`~/.aiplat/plugins/`） | 中 | 租户/利基/第三方，不进核心树 | 通用内核能力 |
| 5 | **MCP Server** | 高 | 外部工具形态、协议边界清晰 | 核心高频路径（应 Tool/Syscall） |
| 6 | **新 Syscall / Core Tool** | 最高 | 基础、通用、不可替代 | 1–5 可行时**禁止**跳级 |

证据：根 `CLAUDE.md` §20；Core §5.24（Hook 0 token → Skill → Tool → MCP）。

### 3.2 运行时角色定义

| 角色 | 是什么 | 典型入口 | 谁调用谁 |
|------|--------|----------|----------|
| **Program / Handler** | 确定性 Python | `handler.py`、Action handler、闸门脚本 | 被 Skill/Action/CI 调用 |
| **Tool** | 原子能力（读文件、HTTP、code…） | `sys_tool_call` → PolicyGate | Agent/Skill 调用；**禁止** Tool 再调 Skill |
| **Skill** | 带 SOP 的能力单元（prompt/handler/hybrid） | `sys_skill_call` → PolicyGate | Agent 或 Stage `skill_name`；**禁止** Skill 嵌套 `sys_skill_call` |
| **MCP** | 外部协议工具集 | MCP 注册 → 暴露为 discovery tools → `sys_tool_call` | 与 Tool 同门禁 |
| **Agent** | 声明 + 运行时循环 + 绑定的 skills/tools | Pipeline stage / Workspace Execute / `create_agent` | 编排 Skill/Tool；不直调其他 Agent（走 handoff/pipeline） |
| **Workflow / Pipeline** | 多 stage 图（chain/router/…） | `PipelineEngine` + team YAML | 编排多个 Agent/Skill/node |
| **Hook** | 确定性事件副作用 | PRE/POST_* | 零 LLM；能 Hook 就不写 Skill |

### 3.3 选用速查

| 你的需求 | 首选 | 次选 | 禁止 |
|----------|------|------|------|
| 「如果 X 则拒绝」类策略 | PolicyGate / 程序规则 | — | 用 LLM 当权限系统 |
| 可复现的文件/API/计算 | Tool 或 handler Skill | MCP（外部系统） | 纯 prompt 假装已执行 |
| 有 SOP 的业务步骤、要 LLM 填语义 | Skill `prompt` 或 `hybrid` | Agent+Skill | 把 SOP 塞进 workflow `config.prompt`（内容归属违规） |
| 多步探索、工具选择、自我纠正 | Agent（`react_tools` / ReAct） | Plan-Execute | oneshot 假装多步 |
| 固定多角色流水线 | Workflow/Pipeline stages | — | Agent 自由 spawn 无门控 |
| 外部 SaaS 工具集 | MCP | 薄 Tool 适配 | 为核心路径新建 Syscall |
| 编码落盘交付 | coding stage defaults + done_verify +（宜）`react_tools` | llm+`uses_file_output`（已有 pre-deploy gate） | 空 DONE 直写盘 |

### 3.4 Pipeline 编排字段（Workflow 侧）

| 字段 | 取值（代码） | 用途 |
|------|--------------|------|
| `pipeline_mode` | `chain` \| `router` \| `parallel` \| `orchestrator` \| `evaluator_optimizer` \| `agent` | 图形态 |
| `routing_mode` | `static` \| `llm` \| `debate` \| `swarm` \| `roundtable` \| `moa` | 动态路由；`llm` 须 opt-in env |
| `execution_mode` | `code_first` \| `tdd` \| `plan_only` | 无 skill_name 时的阶段风格 |
| `node_type` | `agent` \| `llm` \| `code` \| `http` \| `condition` \| `knowledge` \| `tool` \| … | 单节点类型 |
| `debate_*` / `moa_*` | 见 `PipelineStageConfig` | 辩论 / Mixture-of-Agents |

证据：`schemas_builder.PipelineStageConfig`；`pipeline_engine` 路由分支。

---

## 4. Agent 架构：平台用了几种？如何判定？

aiPlat 里「架构」要分清 **三层正交概念**，不要混称。

### 4.1 层 A — 执行混合（`architecture_profile`）【推荐声明】

| Profile | `execution_backend` | `agent_type`（stage） | 含义 |
|---------|---------------------|----------------------|------|
| `oneshot` | `llm` | `react`* | 单次 `sys_llm_generate`，无工具环 |
| `react_tools` | `agent` | `react` | StageRunner → ReActLoop + 工具/技能 |
| `plan_execute` | `agent` | `plan` | Plan→Execute 环 |
| `reflect_loop` | `agent` | `reflection` | 反思环（解析进 plan_execute 族） |

\* oneshot 的 `agent_type=react` 仅填字段；实际不进 ReActLoop。  
证据：`schemas_builder.ARCHITECTURE_PROFILES` + `apply_architecture_profile`。

**升级策略** `upgrade_policy`：`off` \| `signals`（默认）\| `aggressive` — 在重试/错误信号下可把循环形态升级（如 react→plan/reflection）。

### 4.2 层 B — Agent 类工厂（`agent_type` → Python 类）

**权威枚举**（`harness/registry/data/agent_types.yaml`）：

| Canonical | 工厂类（`create_agent`） | 典型循环 |
|-----------|--------------------------|----------|
| `conversational` | `ConversationalAgent` | 对话；偏轻 |
| `react` | `ReActAgent` | `ReActLoop` |
| `plan_execute` | `PlanExecuteAgent` | `PlanExecuteLoop`（含 reflection 别名） |
| `rag` | `RAGAgent` | 检索增强 |
| `multi_agent` | `MultiAgent` | 多 Agent 编排 |
| `materials_chat` | `MaterialsChatAgent` / PipelineAgent | 材料/知识对话管线 |

常用别名：`tool|subagent|code|architect|operator → react`；`plan|reflection|planning → plan_execute`；`review|pure_agent|shell|base → conversational`。

> 旧文档写「8 种类型」：那是运行时别名/历史集合；**登记真相源是上述 6 个 canonical**。

### 4.3 层 C — 能力剖面（`capability_profile`）

等级：`minimal → standard → full → autonomous → collaborative`（+ 显式 `self_evolving` / `persistent`）。  
推断优先级见 [capability-profile.md](capability-profile.md)。  

**与 backend 的真实关系（纠正 agent-system.md 过时说法）**：

1. 默认 `execution_backend = "llm"`（schema 默认值）。  
2. 若设置了 `architecture_profile` → **强制**对应 backend（最高优先）。  
3. `_apply_capability_profile` 可在 `minimal`/`standard` 且无 tools/skills 时把 `agent` **降级**为 `llm`，但 **不会在没有 architecture_profile 时凭空升到 agent**；有 tools/skills 时常推断为 `full`/`autonomous` 并注入 ReAct 能力。  
4. `execution_backend` **不得**由 AGENT.md 随意自定绕过引擎（安全）；团队 YAML / architecture_profile 才是合法钉死方式。

### 4.4 层 D — 编排级「架构」（多 Agent / MoA / Debate）

| 模式 | 触发 | 说明 |
|------|------|------|
| Debate | `debate_participants` 非空 | `_run_debate_stage` |
| MoA | `routing_mode=moa` / `moa_preset` | Mixture-of-Agents；autoreview deep 亦用 |
| Swarm / Roundtable | `routing_mode` | 群体路由变体 |
| Multi-agent team | team YAML 多 stage + handoff | 工厂可出 `agent_manifest.json` |

这些是 **Pipeline 编排架构**，不是单个 AGENT.md 的 `architecture_profile`。

### 4.5 汇总：平台「几种架构」？

| 计数口径 | 数量 | 列表 |
|----------|:----:|------|
| 声明式执行混合 | **4** | oneshot / react_tools / plan_execute / reflect_loop |
| Canonical agent_type | **6** | conversational / react / plan_execute / rag / multi_agent / materials_chat |
| 能力剖面（常用自动） | **5**（+2 显式） | minimal…collaborative + self_evolving/persistent |
| 编排特化 | **若干** | debate / moa / swarm / roundtable / multi-stage team |

日常说「Agent 架构」时，优先指 **层 A（4 种 profile）+ 层 B（6 种 type）**。

---

## 5. 工作区 / 应用工厂生成的 Agent：用几种？如何判断？

### 5.1 工厂显式选择的集合（窄）

`agent_engineering` Skill（生成 AGENT.md 的 SOP）**只要求作者在三者中选 `agent_type`**：

| 选定 | 场景（SOP 原文语义） | 引擎倾向授予的 profile |
|------|----------------------|------------------------|
| `conversational` | 纯对话 | minimal |
| `react` | 需要工具调用的复杂任务 | autonomous |
| `rag` | 以知识检索为主 | full（有 tools/skills 时） |

**明确禁止生成物 frontmatter 乱写**：`capability_profile` / `execution_backend` / 若干门禁字段 — 「引擎根据 agent_type + required_tools/skills 推断」。  
生成 Skill **一律 `execution_type: prompt`**（本 pipeline 不生成 `handler.py`；声明 handler 会注册失败）。平台 media Path0 例外：SKILL.md 仍为 prompt，运行时按规范名绑真实 ffmpeg handler。

证据：`core/engine/skills/agent_engineering/SKILL.md` Step 1 / Step 2 / Step 3；`generated_conformance` 要求 `agent_type`。

### 5.2 生成后实际走到哪条执行路径？

```
AGENT.md agent_type ∈ {conversational, react, rag}
  + required_skills / required_tools
        ↓ team_planner / enrich
PipelineStageConfig（capability_profile 常为 auto → 推断）
        ↓
若团队 YAML 写了 architecture_profile → 层 A 钉死
否则：
  - 默认 backend=llm（oneshot SOP）
  - 有工具/技能且走 Workspace Execute / agent 后端时 → ReAct 环
  - coding：uses_file_output → sandbox + done_verify + autoreview
    · Pipeline llm 路径：gate_llm_file_output_stage 落盘前校验
    · Workspace Execute：inject_workspace_coding_defaults
```

因此：**工厂「声明」3 种 agent_type；「跑起来」仍可能是 oneshot LLM 或 ReAct**，取决于是否进入 `execution_backend=agent`、是否绑定工具/技能、团队是否钉 `architecture_profile`。

### 5.3 团队种子可钉的架构（超出工厂三选一）

例：`workspace_seeds/teams/code_split.yaml` 可对编码 stage 设 `architecture_profile: plan_execute`。  
这是 **平台团队配置**，不是 agent_engineering 默认生成字段。

### 5.4 工作区手跑 Agent（非工厂流水线）

| 路径 | 架构判定 |
|------|----------|
| Workspace Execute | 读取 AGENT.md → create_agent / StageRunner；`inject_workspace_coding_defaults` 在 `uses_file_output` 或 `coding_closed_loop` 时注入工厂等价闭环 |
| 显式 `coding_closed_loop: false` | 退出闭环注入 |
| 仅有 `coding_policy_profile` | **不**单独视为 opt-in |

证据：`schemas_builder.inject_workspace_coding_defaults`；CoreFacade 工作区后台执行接线。

### 5.5 生成物架构决策表（给评审用）

| 问题 | 判定 |
|------|------|
| 只要问答、无工具？ | `conversational` + 预期 minimal / llm oneshot |
| 要调工具/多步？ | `react` + 声明 `required_tools`/`required_skills`；团队宜加 `architecture_profile: react_tools` |
| 主路径是检索？ | `rag` |
| 要 peer-review 后再 DONE？ | **不要**依赖 llm oneshot；用 `react_tools` / agent backend（review_gate 需要 follow-up） |
| 要确定性媒体处理？ | Skill 名对齐平台 media canonical；prompt 声明 + Path0 handler |
| 要 handler 业务逻辑？ | 当前工厂 **不生成** handler.py → 用手写 Skill 或扩展平台 handler，勿在生成物里假称 handler |

---

## 6. 端到端判定清单（实施 / Code Review）

按顺序问：

1. **这件事能否 100% 用规则/代码表达？** → 是：Hook / handler / Tool / 闸门；否：下一步。  
2. **是否只需单次语义生成、无工具？** → `prompt` Skill 或 `architecture_profile=oneshot`。  
3. **是否需要多步工具/技能？** → Agent + `react_tools`（或 plan_execute / reflect_loop）。  
4. **是否多角色固定流水线？** → Workflow/Pipeline；契约用 handoff + schema 门。  
5. **能力是否外部系统？** → MCP（或薄 Tool）；证明不能落在阶梯 1–4。  
6. **是否编码落盘？** → 强制 coding defaults；优先 agent 环；llm 路径依赖 pre-deploy done_verify。  
7. **是否生成物？** → 只选 agent_type∈{conversational,react,rag}；Skill 用 prompt；架构钉死放团队 YAML。

---

## 7. 配置与环境变量附录

| 键 | 作用 |
|----|------|
| `architecture_profile` | 钉死执行混合（最强） |
| `execution_backend` | `llm` \| `agent` |
| `upgrade_policy` | `off` \| `signals` \| `aggressive` |
| `capability_profile` | `auto` 或显式等级 |
| `agent_type` | 类工厂 + 推断输入 |
| `execution_type`（SKILL.md） | handler / hybrid / prompt / … |
| `meta_tool` | 偏码执行 |
| `done_verify` / `review_gate` / `uses_file_output` | 完成与编码闭环 |
| `routing_mode` / `pipeline_mode` / `debate_*` / `moa_*` | 编排 |
| `AIPLAT_META_TOOL_*` | meta-tool 开关 |
| `AIPLAT_DONE_VERIFY*` | DONE 门 |
| `AIPLAT_CODING_STAGE_*` | 编码 stage 默认 |
| `AIPLAT_DYNAMIC_ROUTER_ENABLED` | llm 动态路由 opt-in |
| `AIPLAT_EXECUTION_AUDIT` | skill actual_mode 审计 |
| `AIPLAT_PROFILE_CALIBRATE` | profile 运行时校准 |

---

## 8. 与旧文档的已知张力（以本文 + 代码为准）

| 旧说 | 现状 |
|------|------|
| 「capability_profile 替代 binary execution_backend」 | 两者共存；profile 注入能力并可降级 backend；architecture_profile 才强制混合 |
| 「backend 仅由 capability_profile 决定」 | 否；默认 llm + profile 推断 + architecture_profile 覆盖 |
| 「8 种 agent_type」 | 登记 6 canonical + 别名 |
| 「工厂会选 execution_backend」 | 工厂 SOP 明确不写；由引擎/团队 YAML 决定 |

---

## 9. 演进槽（尚未或局部接线——勿当现状）

| ID | 想法 | 验收标准（将来） |
|----|------|------------------|
| E1 | 工厂生成可选写出 `architecture_profile` | conformance 白名单 + agent_engineering Step 更新 |
| E2 | 生成物支持 `execution_type: handler` 的代码 stage | 工厂增加编码 stage 产 handler.py |
| E3 | 统一「决策追踪」字段进 trace | stage 事件带 `decision={profile,backend,execution_type}` |
| E4 | Semgrep/静态规则辅助选路径 | CI 对「prompt Skill 宣称写文件」告警 |

变更 E* → 实装后移入正文对应节，并删演进槽行。

---

## 10. 变更记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-10-11 | 首版：统一 LLM/程序、阶梯、三层 Agent 架构、工厂三选一与运行时路径；纠正 agent-system 过时 backend 说法 |
