---
doc_type: Architecture
title: 外源资产互通完整改善方案（Agent / Skill / Tool / MCP）
status: proposed
authority: design-target
language: zh-CN
created: 2026-11-12
---

# 外源资产互通完整改善方案（Agent / Skill / Tool / MCP）

> **本文是设计目标态方案，不是实施 diff。**  
> **阅读方式**：先读 **§0 白话版**（产品/管理者/使用方）；从 **§1 起**才是给实施与评审用的专业说明。

---

## 0. 白话版：这方案到底在说什么？

### 0.1 用一句话说

外面的好技能，**导入后就要像在 Cursor 里一样马上能用**（让助手按说明书干活）。  
审核仍然要做，但审核主要管「能不能当正式/生产能力上架」，**不能变成「装进来却用不了」**。  
只有少数情况（要乱改文件、跑危险命令、缺关键插头）才进入「还差几步 / 不能用」。

### 0.1b 产品默认承诺（非常重要）

| 承诺 | 说明 |
|------|------|
| **默认能用** | 开源里最大头的「说明书型 Skill」（如 grill-me）→ 导入成功 = **立刻可调用**，体验对齐 Cursor |
| **审核不挡试用** | 审核/上架管的是「正式发布、生产租户、高权限」；**开发/工作区试用不应被审核卡住** |
| **少数才降级** | 只有安全扫描不过、或非用危险能力不可的，才「不能用 / 还差几步」 |
| **导入要有意义** | 若主流导入结果都是不能用，则导入功能失败——这是本方案要避免的 |

> 一句话校正：档位机制是为了**少数例外说实话**，不是为了让**多数好技能进门坐冷板凳**。

### 0.2 四个东西分别是什么（不用记英文）

| 名字 | 可以把它想成 | 生活类比 |
|------|-------------|---------|
| **Agent（智能体）** | 一个有角色设定的助手 | 请来的「岗位员工」：有人设、有职责 |
| **Skill（技能）** | 一套做事步骤说明 | 员工手里的「SOP 手册」 |
| **Tool（工具）** | 系统里能真正动手的能力 | 打印机、搜文件、跑命令这些「设备」 |
| **MCP** | 接外面工具箱的标准插头 | 把公司外的设备用统一插座接进来 |

开源社区里大量「好东西」，多数其实是**写得好的说明书**（尤其是 Skill）。  
在 Cursor 里「立即能用」，靠的也主要是：**助手读说明书并照着做**——不是先写一套复杂平台程序。aiPlat 对这类资产应对齐同一体验。

### 0.3 现在哪里不舒服？

1. 管理画面可以「从 GitHub 导入」，看起来很方便。  
2. 但导入成功，有时只表示「文件拷进来了」，**用起来却别扭或不知能不能调**。  
3. 有的还会自动「改装」一下，看起来能跑，**实际可能和原作者想的不一样**（假顺畅）。  
4. 若方案又强调「大量待升格」，会让人觉得：**导入没意义**——这正是要改掉的产品偏差。

### 0.4 我们主张怎么做？（四句话）

1. **能进来**：认简单格式（有名字、有说明、有步骤就行）。  
2. **进来就能用（默认）**：说明书型 → 立刻可调用，接近 Cursor。  
3. **审核管上架，不管「第一次能不能试」**：先用起来，再走正式审核（生产/高权限另算）。  
4. **真危险才拦住**：改系统、跑任意命令、未映射的高危能力 → 才「还差几步 / 不能用」。

### 0.5 「档位」用大白话（默认是绿的）

| 你在界面上看到 | 占比预期 | 含义 |
|----------------|:--------:|------|
| **现在就能用** | **大多数** | 导入后马上可让助手按流程干活（对齐 Cursor 的「说明书即能力」） |
| **还差几步** | 少数 | 缺依赖、要接 MCP、或要确认高权限；**应列出差什么、怎么补** |
| **不能用** | 极少数 | 安全扫描失败等；必须给原因 |

专业文档里的 `prompt_ready` 等英文名，只是内部标签；**产品默认文案应是「现在就能用」**。

**审核怎么放才不影响「能用」：**

| 层次 | 能不能用 | 要不要审核 |
|------|:--------:|:----------:|
| 工作区导入后试用 / 开发联调 | ✅ 立刻能 | 可不挡 |
| 标成「已审核/生产可用/高权限」 | ✅ 能 | ✅ 要 |
| 安全扫描失败 | ❌ | — |

### 0.6 改善之后，你能感到的变化

| 以前常见感觉 | 以后应该变成 |
|--------------|--------------|
| 导入了却不知道怎么用 / 用不了 | **说明书型：导入完就能点名调用**（像 Cursor） |
| 「导入成功了」——然后呢？ | 默认显示 **现在就能用**；少数才显示待办 |
| 一提治理就像什么都不能跑 | **试用畅通；上架/高权限才审核** |
| 带危险能力的技能瞎跑或假跑 | 这类才进「还差几步」，并写清差什么 |
| 接了外部工具箱断线还装会 | 断线就不可用，不装会 |

### 0.7 这个方案不是什么

- **不是**「导入后多数不能用，只有升格后才能用」——那会让导入失去意义。  
- **不是**保证和 Cursor 每一个私有开关都一模一样；但**主路径体验要对齐：说明书 → 立即可用**。  
- **不是**取消审核；审核挡的是**正式背书与高风险权限**，不是挡**第一次使用**。  
- **不是**默认执行外面随便下载的程序代码。

### 0.8 谁读后面章节？

| 读者 | 建议 |
|------|------|
| 产品 / 管理者 / 想先懂意图的人 | **读完 §0 即可**；需要时再扫 §11「改善后变化」 |
| 架构评审 / 开发实施 | 继续读 §1 之后的专业方案；实施时必须以 §0.1b 默认承诺为准 |

---

## 1. 问题定义

### 1.1 现状（As-Is）

aiPlat 已具备多条「能装进来」的能力，但未形成统一、诚实、可调度的互通契约：

| 已有能力 | 位置（示意） | 现状评价 |
|---------|-------------|---------|
| GitHub / 本地 / zip 安装 | workspace skills installer、ImportBar | 能拉、能拷，成功语义偏「落盘成功」 |
| 格式转换 | `format_adapters.py`、`agentskills_parser.py` | 能转 SKILL.md / AGENT.md / MCP yaml |
| Skill 形态适配 | `skill_adapter.adapt_skill` | 有 PURE_PROMPT / SCRIPT / TOOL 分流；结果未成为一等公民 |
| Marketplace 外源发现 | `SkillMarketplace.discover_external`（agentskills.io） | 发现与安装、档位、调度未闭环 |
| MCP 连接与工具列表 | 管理台 MCP、PolicyGate 路径 | 协议层正确，但与「外源导入档位」未统一 |
| Agent / Skill 目录注册 | `~/.aiplat/agents`、`~/.aiplat/skills` | 注册存在；「可调度」条件不透明 |

### 1.2 核心矛盾

1. **交换格式轻**（开源多为 name + description + SOP/配置）  
2. **平台执行模型重**（权限、syscall、handler、审批、评测）  
3. 现状用「安装/适配成功」模糊掩盖了 1 与 2 的差距 → 用户以为「装上就能像原生态一样用」。

### 1.3 要回答的产品问题

> 任意符合公约的外源资产进入 aiPlat 后：  
> - **默认立刻能用**（尤其说明书型 Skill，体验对齐 Cursor）；  
> - 能看见档位；少数「还差几步 / 不能用」必须给原因与修复动作；  
> - **审核管上架与高权限，不挡工作区试用**；  
> - 高副作用能力有升格路径；**绝不**因启发式转换假绿。

---

## 2. 设计原则（不可妥协）

| # | 原则 | 含义 |
|---|------|------|
| P0 | **导入默认可用** | 说明书型 Skill（及等价低风险资产）导入成功 ⇒ 默认可调度；「不能用」是例外不是常态 |
| P1 | 交换与执行分离 | 外源只提供声明；执行权只在 aiPlat 运行时 |
| P2 | 一个管道，四类资产 | Agent/Skill/Tool/MCP 共用 L0→L1→L2，不按生态各写执行器 |
| P3 | 试用与上架分离 | 可调度（能试用）与已审核上架（生产背书）分开；审核不默认阻断第一次使用 |
| P4 | 映射优先于重写 | Tool 优先映射到平台能力或 MCP 投影；禁止默认执行任意外源代码 |
| P5 | 自动生成最多是草稿 | 自动 handler / 猜测 schema 不得默认启用为生产执行 |
| P6 | 跨资产依赖可解析 | Agent 依赖的 Skill/Tool、Skill 依赖的 Tool、MCP 投影 Tool 必须可查询 |
| P7 | 安全门禁唯一 | 本地 Tool 与 MCP 投影 Tool 一律 PolicyGate（+ 既有 Approval 路径） |
| P8 | 诚实对外 | 管理台展示「现在就能用 / 还差几步 / 不能用」；禁止只有「安装成功」 |

---

## 3. 目标架构：三层模型

```
┌─────────────────────────────────────────────────────────────┐
│ L0 Interchange（交换层）                                       │
│  公约文件：AGENT.md / SKILL.md / tool schema / MCP server 描述   │
│  来源：GitHub、agentskills.io、zip、本地目录、MCP 注册表          │
└───────────────────────────┬─────────────────────────────────┘
                            │ validate + detect
┌───────────────────────────▼─────────────────────────────────┐
│ L1 Compatibility（兼容层）                                    │
│  形态检测、工具/依赖映射、安全扫描、写出 _compat（tier 一等公民）  │
│  升格工作流：mapped / handler / bound_ready                     │
└───────────────────────────┬─────────────────────────────────┘
                            │ register with tier
┌───────────────────────────▼─────────────────────────────────┐
│ L2 Platform Runtime（平台运行时）                              │
│  AgentRuntime / SkillExecutor / ToolRegistry / MCP Client     │
│  仅调度就绪档位；一律平台门禁                                   │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 L0 — 交换公约（各资产最小进口形状）

| 资产 | L0 最小要求 | 可选增强 |
|------|------------|---------|
| **Skill** | 目录 + `SKILL.md`；frontmatter 含 `name`、`description`；body=SOP | license、scripts/、references/ |
| **Agent** | `AGENT.md` 或可转换的 `SOUL.md`/`AGENTS.md`；含名称与职责/人设 | 声明依赖的 skill/tool 名列表 |
| **Tool** | 名称 + 描述 + JSON Schema（input）；副作用声明（read/write/net/exec） | output schema、examples |
| **MCP** | 可解析的 server 连接描述（stdio/sse/http 等） | 工具白名单、环境变量清单 |

说明：L0 **不要求** aiPlat 全量 frontmatter（permissions、完整 input_schema 对象化等）。全量字段是 L1/L2 升格产物，不是进口门槛。

### 3.2 L1 — 兼容档位（Compat Tiers）

#### Skill

| Tier | 含义 | 默认可调度？ |
|------|------|:---:|
| `prompt_ready` | 纯 SOP，可走 LLM+prompt 执行 | ✅ |
| `tool_mapped` | SOP + 工具引用已全部映射到平台 Tool/Syscall | ✅ |
| `needs_handler` | 需要确定性脚本/副作用，尚无合格 handler | ❌（可见，待升格） |
| `blocked` | 安全扫描失败或关键能力不可降级缺失 | ❌ |

#### Agent

| Tier | 含义 | 默认可调度？ |
|------|------|:---:|
| `persona_ready` | 人设/SOP 足够；**导入后默认档**（对齐 Cursor：读人设即可聊） | ✅ 对话/试用立刻可用 |
| `bound_ready` | 声明的 Skill/Tool 均已解析且可调度 | ✅ 全功能（流水线/团队） |
| `needs_binding` | 仍缺部分依赖 | ⚠️ **对话仍可用**；仅全功能路径受限（须列出缺什么） |
| `blocked` | 安全/策略拒绝 | ❌ |

> **校正**：`needs_binding` **不得**理解成「Agent 完全不能用」。缺依赖只挡需要这些依赖的能力，不挡基于人设的即时对话。

#### Tool

| Tier | 含义 | 默认可调度？ |
|------|------|:---:|
| `mapped` | 已映射到平台 Tool 或 MCP 投影 | ✅ **立刻可 `sys_tool_call`** |
| `schema_only` | 仅有描述/schema，供规划 | ❌ 真实调用拒绝（须提示改走映射/MCP） |
| `needs_impl` | 需要实现草稿或人工接入 | ❌；有草稿时走「确认启用」（同 §5.4 精神） |
| `blocked` | 危险/违规 | ❌ |

> **校正**：Tool 的「像 Cursor 一样立刻能用」= **映射成功或 MCP 已连接并投影** 后立刻能调；**不是**任意外源 `.py` 热加载。

#### MCP

| Tier | 含义 | 默认可调度？ |
|------|------|:---:|
| `connectable` | 配置合法，握手中/未握手 | ❌（应**自动尝试连接**，少停留） |
| `connected` | 握手成功，工具已投影 | ✅ **默认立刻可用**（最小权限）；高风险工具可个别 gated |
| `gated` | 已连接，部分工具被策略禁用 | 部分可用 |
| `blocked` | 连接拒绝或拉黑 | ❌ |

> **校正**：添加 MCP 配置后应**自动连接**；连上即用。审核管上架/放宽高风险工具，不挡第一次连上试用。

### 3.3 L2 — 平台运行时绑定（唯一执行面）

| 资产 | 唯一执行入口 | 禁止事项 |
|------|-------------|---------|
| Skill | `SkillExecutor` / `sys_skill_call` | 直接解释执行外源 Bash/私有 runtime |
| Agent | AgentRuntime（ReAct 等既有类型） | 嵌入外源 agent loop 进程为默认路径 |
| Tool | `ToolRegistry` → PolicyGate | `eval`/动态 import 外源任意代码为默认安装结果 |
| MCP | 平台 MCP Client → 投影 Tool → PolicyGate | MCP 工具绕过门禁；无限挂载无上下文预算 |

---

## 4. 统一数据模型：`_compat`（一等公民）

每个导入资产目录（或等价 registry 记录）必须持久化兼容描述。建议写入资产 sidecar 或 frontmatter 保留段（实现二选一，**语义必须统一**）。

### 4.1 通用字段

```yaml
_compat:
  schema: aiplat.asset_compat.v1
  asset_kind: skill | agent | tool | mcp
  source:
    type: github | agentskills.io | zip | local | mcp_registry
    uri: "https://github.com/org/repo"
    ref: "abc1234"
    subpath: "skills/grill-me"
  detected_format: agentskills | hermes | cursor_agents | mcp_json | aiplat_native
  tier: prompt_ready
  schedulable: true          # 由 tier + 策略计算，禁止手写撒谎
  issues:                    # 阻断或降级原因
    - code: missing_tool_mapping
      severity: warning | error
      message: "SOP references Bash; no safe mapping"
  mappings:                  # 外源名 → 平台名
    - from: Bash
      to: code_execution
      critical: false
  missing_critical: []
  dependencies:              # 跨资产
    - kind: tool
      name: file_read
      status: resolved | missing | not_schedulable
  upgrade:
    recommended: needs_handler | bind_tools | connect_mcp | none
    auto_generated_artifacts: []   # 若有自动 handler 草稿路径，列在此且默认 disabled
  adapted_at: "2026-11-12T12:00:00Z"
  adapter_version: "1.0.0"
```

### 4.2 调度判定（伪规则）

```
schedulable(asset) :=
  asset.tier ∈ SchedulableTiers[asset.kind]
  AND asset.blocked == false
  AND all(dep.status == resolved AND dep.schedulable for dep in required_deps)
```

Registry 的 `list_for_router()` / Agent 绑定时 **只返回 schedulable=true**；完整列表走 `list_all(include_pending=true)`。

---

## 5. 统一导入管道（四类共用）

```
1. Ingest        拉取到 staging（git clone / unzip / 读本地 / MCP 配置提交）
2. Detect        FormatAdapter 识别资产包（可含多类）
3. SecureScan    路径穿越、密钥文件、危险脚本、权限声明审计
4. L0Validate    公约文件存在且可解析
5. Adapt         分资产适配器：映射、补最小字段、生成 _compat（不默认启用草稿 handler）
6. Persist       写入 ~/.aiplat/{agents|skills|tools|mcp}/...
7. Register      写入对应 Registry，带 tier
8. Report        返回 InstallReport（installed / pending_upgrade / blocked）
9. Optional QA   「测试审核上架」工作流（生产租户强制；开发可跳过但 UI 标黄）
```

### 5.1 InstallReport（API/UI 统一返回）

```json
{
  "ok": true,
  "assets": [
    {
      "kind": "skill",
      "id": "grill-me",
      "tier": "prompt_ready",
      "schedulable": true,
      "actions_required": []
    },
    {
      "kind": "agent",
      "id": "research_agent",
      "tier": "needs_binding",
      "schedulable": false,
      "actions_required": ["bind_skill:web_search", "map_tool:Bash"]
    }
  ],
  "blocked": [],
  "warnings": ["auto_handler_draft_created_but_disabled:foo"]
}
```

改善后：**禁止**仅返回 `{installed: ["grill-me"]}` 而不带 tier。

### 5.2 自动 handler / 代码生成策略（纠正现状风险）

| 行为 | 目标态 |
|------|--------|
| 检测 SCRIPT_BASED | 可生成 `handler.py.draft` + 升格任务 |
| 默认 `handler.py` 覆盖并 `execution_type=handler` | **禁止**作为默认 |
| 用户在升格向导确认 + 安全扫描通过 | 才启用 handler 并改 tier |

### 5.3 无 `handler.py` 能否用？（讨论结论，必须写清）

| 技能形态 | 要不要 `handler.py` | 导入后 |
|----------|:-------------------:|--------|
| 说明书型（prompt） | **不要** | **自动即可用**（读 SKILL.md SOP → LLM 执行），对齐 Cursor |
| 程序型（handler） | **要** | 无合格 handler 前不按 handler 调度；可先降级 prompt（若 SOP 足够）或进待升格 |

**结论**：没有 `handler.py` 是开源 Skill 的常态，也是「导入即能用」的主路径；**不是缺陷**。

### 5.4 「确认启用」handler 草稿的产品流程（讨论结论）

仅当系统判断需要 handler（或已生成草稿）时才走本流程。说明书型 **不需要** 这一步。

1. 导入结果提示：**还差几步** · 已有 handler 草稿（未启用）  
2. 打开升格页，展示：草稿做什么、权限清单、与原 SOP 的差异/警告  
3. 可选：样例试跑  
4. 用户（或管理员）点击 **「启用 handler」** → 草稿转正、写入审计（谁/何时）  
5. 档位变为可调度（handler 路径）；若还需生产上架，另走审核（不挡工作区试用）

**确认 = 管理台显式「启用」操作**，不是口头同意，也不是导入时静默生效。

---

## 6. 分资产详细方案

### 6.1 Skill

**进口**  
- 主公约：agentskills / skills.sh 族 `SKILL.md`  
- 转换：保留 SOP body；只补 L1 最小字段（`execution_type` 默认 `prompt` 等）  
- `_compat.tier` 由形态检测决定，不靠「猜 IO schema」决定可否调度  
- **无 `handler.py` 时默认 `prompt_ready` 且 schedulable=true**（安全扫描通过的前提下）

**执行**  
- `prompt_ready`：现有 prompt 路径（**无需 handler.py，全自动**）  
- `tool_mapped`：prompt + 白名单 tools（映射表）  
- `needs_handler`：管理台可见；可保留草稿；未启用前 `sys_skill_call` 若强制 handler 则返回 `skill_not_schedulable`，并给出「去启用/去映射」动作

**改善后变化**  
- grill-me 类开源 Skill：导入即可调度（prompt），**与 Cursor「读说明书即用」同构**  
- 带 Bash/写文件且无法安全映射的 Skill：进入待升格；**不阻塞其它已 prompt_ready 的技能**  
- 假绿自动 handler 消失；启用必须经 §5.4 确认

### 6.2 Agent

**进口**  
- `AGENT.md` 原生，或 Hermes `SOUL.md`+`AGENTS.md` → AGENT.md（已有转换能力，纳入统一报告）  
- 解析 `required_skills` / `tools` / 文中工具名 → `dependencies[]`  
- 安全扫描通过后：**默认 `persona_ready`，对话立刻可试**（对齐 Cursor 加载人设即聊）

**执行**  
- `persona_ready` / 带缺口的 `needs_binding`：**对话/试用立刻可用**（自动，无需先绑齐全部依赖）  
- `bound_ready`：才进团队/流水线等全功能路径  
- 缺依赖时 UI 标明「聊天可用，下列能力暂不可用」，并一键去补 Skill/Tool/MCP  
- 依赖降级 → 全功能降为 `needs_binding`，**但不得把对话也关掉**（除非 `blocked`）

**确认/审核**  
- 导入后对话：**无需确认**  
- 生产上架 / 授予高权限工具：**要审核**（不挡第一次聊）

**改善后变化**  
- 外源 Agent：**进来就能聊**；不是「先绑完依赖才能碰」  
- 全流程能力仍诚实：缺什么显示什么，而不是假称全能

### 6.3 Tool

**进口三种合法路径（按优先级）**

1. **映射到平台已有 Tool**（名称/能力等价）→ `mapped` → **立刻可调用**（自动）  
2. **作为 MCP 工具投影**（外源本就是 MCP）→ 随 MCP `connected` → **立刻可调用**（自动，经 PolicyGate）  
3. **schema_only 入库** → 可被模型「看见」；真实调用拒绝并提示走 1/2  

**明确不做为默认的路径**  
- 下载任意 GitHub `.py` 动态加载进主机进程

**确认**  
- 映射命中 / MCP 投影：**无需额外确认即可用**（默认最小权限）  
- 自动生成的本地实现草稿：同 §5.4，**点「启用」后才可调度**  
- 放宽高风险 effects（写盘/任意执行）：要确认或审批  

**改善后变化**  
- 「能用」的定义说清：映射或 MCP 连上 = 能用；只有 schema = 还不能当工具调  
- 不把「不能热加载任意 py」误说成「Tool 导入没用」——有用路径是映射/MCP

### 6.4 MCP

**进口**  
- mcp.json / server.yaml / 管理台表单 → 统一成平台 server 配置  
- 保存后 **自动发起连接**（少停留在 `connectable`）  
- 成功：`connected`，`tools/list` 投影为平台 Tool → **默认立刻可用**

**执行**  
- 投影 Tool 一律 PolicyGate；默认最小权限  
- 高风险工具可先 `gated`，在详情里 **确认放行**（个别启用，不是整站不能用）  
- 上下文预算：server 数 / 描述 token 可配置  

**确认/审核**  
- 连接成功后的常规只读类工具：**自动能用**  
- 高风险工具放行、生产上架：确认/审核  
- 断连：投影 Tool `unavailable`，不假成功  

**改善后变化**  
- 加 MCP ≈ 插上插头并自动通电；通了就能用工具  
- 审核不挡「第一次连上试用」
---

## 7. 跨资产依赖与级联

### 7.1 依赖图

```
Agent
  ├── requires Skill*  → Skill.schedulable
  └── requires Tool*   → Tool.schedulable (含 MCP 投影)

Skill
  └── requires Tool*   → 映射成功则 tool_mapped；否则降级/待升格

MCP Server
  └── projects Tool*   → connected 后 Tool.mapped(source=mcp)
```

### 7.2 级联规则

| 事件 | 级联 |
|------|------|
| Skill 从 schedulable→否 | 依赖它的 Agent：`bound_ready`→`needs_binding` |
| MCP 断开 | 投影 Tool → unavailable；依赖 Agent/Skill 重算 |
| Tool 映射被管理员撤销 | 引用方重算 tier |

需要后台 **CompatRecomputer**（安装后、启用/禁用、MCP 状态变更时触发）。

---

## 8. 发现与生态源（完整目标，非单源）

| 源 | 用途 | 目标态 |
|----|------|--------|
| agentskills.io 索引 | Skill 发现 | discover → 选定 → 同一 Install 管道；结果带 tier |
| GitHub/Git URL | 任意 monorepo | subpath 选择 Agent/Skill/MCP；多资产一次 InstallReport |
| zip / 本地目录 | 离线/内网 | 同管道 |
| MCP 注册表/目录（可配置） | Server 发现 | 仅配置发现；连接仍本地确认 |
| 平台能力市场（内采） | 已审核资产 | tier 预置为生产档，仍保留 _compat 溯源 |

原则：**发现可多样，安装与调度契约唯一。**

---

## 9. 安全、权限与治理

1. **SecureScan（强制）**：密钥文件、绝对路径写系统盘、明显远程执行载荷 → `blocked`  
2. **权限默认最小**：导入 Skill `permissions: []` 或只读；升格时显式加权限  
3. **生产租户**：`needs_*` 不可上架到「已发布」；必须 QA 工作流  
4. **审计**：记录 source uri/ref、adapter_version、谁批准了升格  
5. **MCP**：server 数/描述 token 预算；高风险 tool effects 默认审批  

---

## 10. 管理台与 API 改善（用户可见变化）

### 10.1 管理台

| 页面/组件 | 改善后 |
|-----------|--------|
| 导入（ImportBar / AddSkill / AddAgent） | 结果页按资产列出 tier、schedulable、下一步动作 |
| Skill/Agent/Tool/MCP 列表 | 列：档位徽章、来源、依赖健康、是否可调度 |
| 资产详情 | `_compat` 全文、映射表、缺失依赖、升格按钮 |
| 「待升格」队列 | 聚合所有 needs_* / draft handler |
| MCP | 连接状态与投影工具权限矩阵 |
| 能力市场 | 外源发现与本地档位状态并排，禁止「一键安装即生产」文案 |

### 10.2 API（契约级）

- `POST .../installer/install` → **必须**返回 `InstallReport`  
- `GET .../{kind}/{id}/compat` → 返回 `_compat`  
- `POST .../{kind}/{id}/upgrade` → 升格动作（bind / map_tools / enable_handler / connect）  
- `GET .../registry?schedulable=true` → 路由专用  
- 调用未就绪 Skill/Tool → 稳定错误码：`asset_not_schedulable` + tier + actions_required  

---

## 11. 运行时行为改善（改善后有什么变化）

### 11.1 对照表（Before → After）

| 场景 | 改善前 | 改善后 |
|------|--------|--------|
| 从 GitHub 导入 grill-me 类纯 SOP | 可能装上；触发/可用性说不清 | `prompt_ready`，可被 Agent `sys_skill_call`；Cursor 私有字段忽略 |
| 导入含 Bash/写盘的 Skill | 可能自动 handler 或静默 prompt 假跑 | `needs_handler` 或 `tool_mapped`；未就绪调用明确失败 |
| 导入 Hermes Agent | 转成 AGENT.md，列表可见 | 依依赖解析为 `persona_ready`/`needs_binding`/`bound_ready` |
| 导入「Tool 代码」 | 边界模糊 | 默认只能 mapped / schema_only / MCP；无默认动态加载 |
| 添加 MCP Server | 能连、能列工具 | tier 生命周期清晰；投影 Tool 统一门禁；断连不可假成功 |
| Agent 路由选 Skill | 可能选到未适配好的 | 只选 `schedulable=true` |
| 管理台「安装成功」 | 易误解为可用 | 展示「可调度 / 待升格 / 已阻断」三态 |
| 开源生态预期 | 「规范太重进不来」或「进来了不能用」 | 「轻资产能用；重能力可升格」 |

### 11.2 对开发者/FDE 的体验变化

- **找世界开源能力**：市场/URL 导入 → 立刻知道能不能用、差什么  
- **做方案拷问类能力**：prompt Skill 当天可用  
- **做改仓库/跑命令类能力**：必须走升格 + 权限，不再碰运气  
- **接企业 MCP**：成为接外部工具的主路径，而不是复制 Tool 实现  

### 11.3 对平台治理的变化

- 外源资产有溯源（uri/ref/adapter_version）  
- 生产发布与「开发试装」分离  
- 架构审计可增加：`schedulable` 与 `execution_type` 一致性、禁止无 _compat 的导入资产进生产路由  

---

## 12. 与现有实现的映射（如何改、仍不直接改代码）

| 现有模块 | 目标态职责 |
|---------|-----------|
| `skill_installer.py` | 成为统一 Ingest/Persist 的 Skill 分支；输出 InstallReport |
| `skill_adapter.py` | 只负责检测+写 `_compat`+最小 frontmatter；自动 handler 改为 draft |
| `agentskills_parser.py` / `format_adapters.py` | 保留为 L0→平台文件转换；转换后必须跑 Compat 步骤 |
| `SkillRegistry` / `SkillExecutor` | 增加 schedulable 过滤与 `asset_not_schedulable` |
| `agent_manager` / Agent 发现 | 解析依赖 + 级联重算 Agent tier |
| Tool registry + permission | 支持 mapped/schema_only；拒绝调度 schema_only |
| MCP 管理 | 状态机写入 MCP `_compat`；投影 Tool 标注 source |
| `SkillMarketplace` | discover_external 接到同一 Install；展示远端元数据≠本地 tier |
| 管理台 ImportBar 等 | 按 InstallReport 渲染；待升格队列 |

---

## 13. 分阶段交付（完整目标下的工程切片）

> 切片是为了可交付，**不是**把目标裁成「永远最小闭环」。每阶段都必须朝同一契约前进。

### Phase A — 契约落地（Skill 先行，但模型通用）

- 定义 `aiplat.asset_compat.v1`  
- Skill 导入强制写 `_compat`；InstallReport 含 tier  
- Registry/Executor 硬过滤；错误码稳定  
- 关闭「自动启用生成 handler」默认行为  
- 管理台 Skill 列表/导入结果展示档位  

**验收**：导入 agentskills 纯 SOP → `prompt_ready` 可调用；含未映射关键工具 → 不可调度且原因可见。

### Phase B — Agent 依赖与级联

- Agent `_compat` + dependencies 解析  
- CompatRecomputer 级联  
- `persona_ready` vs `bound_ready` 入口策略  
- 管理台 Agent 绑定向导  

**验收**：缺 Skill 的外源 Agent 不能进流水线；补齐依赖后自动升为 `bound_ready`。

### Phase C — Tool 映射模型 + MCP 生命周期

- Tool 三路径（map / mcp / schema_only）  
- MCP tier 状态机 + 投影 Tool 门禁 + 断连级联  
- 上下文预算策略配置化  

**验收**：MCP 工具与本地 Tool 同审计；schema_only 调用被拒；MCP 断连后调用失败信息正确。

### Phase D — 生态发现与治理闭环

- agentskills.io 发现→安装→档位全链路  
- 生产租户 QA/上架门禁  
- 审计报表、能力市场文案与状态对齐  
- 架构守卫：生产路由禁止无 `_compat` 外源资产  

**验收**：从外源索引到可调度/待升格的路径可演示；生产误用未就绪资产被阻断。

---

## 14. 验收标准总表（Definition of Done）

| # | 标准 |
|---|------|
| 1 | 任一安装 API 返回结构化 InstallReport（含 tier/schedulable/actions） |
| 2 | 四类资产均有可查询 `_compat` |
| 3 | 默认路由/执行面只使用 schedulable 资产 |
| 4 | 未就绪调用返回稳定错误码与修复动作 |
| 5 | 自动生成执行代码默认不启用 |
| 6 | MCP 投影 Tool 100% 经 PolicyGate |
| 7 | 依赖变更触发级联重算（有测试） |
| 8 | 管理台可区分：可调度 / 待升格 / 已阻断 |
| 9 | 文档与 UI 文案不再声称「导入即与原生态完全一致」 |
| 10 | 至少 3 个真实外源样例纳管：纯 SOP Skill、含工具 Skill、MCP server、外源 Agent 包 |

---

## 15. 风险与非目标

### 非目标

- 保证任意 LangChain/LlamaIndex Tool 类可热加载执行  
- 保证 Cursor `disable-model-invocation` 等字段语义原样生效  
- 用启发式保证外源脚本与原文等价  

### 风险

| 风险 | 缓解 |
|------|------|
| 用户觉得「装了却不能用」 | UI 强调三态 + 一键升格；prompt_ready 覆盖多数优质 SOP |
| 适配器误判 tier | 检测可解释；允许手动降级/升级审计 |
| 依赖级联抖动 | 重算幂等；批量变更合并 |
| MCP 上下文膨胀 | 预算策略 + 推荐 server 上限 |

---

## 16. 结论

本方案给出的不是「再写一个导入按钮」，而是：

**以 L0 开放交换公约进口世界资产 → 以 L1 兼容档位诚实表达可用性 → 以 L2 平台运行时唯一执行。**

覆盖 **Agent、Skill、Tool、MCP** 四类；与现有 installer/adapter/MCP/门禁能力对齐；纠正「安装成功=可用」和「自动 handler 假兼容」两条实现歧途。

改善后的本质变化是：

> **aiPlat 从「能把外源文件拷进来的平台」，变成「能按真实兼容档位使用全球 Agent/Skill/Tool/MCP 的平台」。**

---

## 17. 建议的下一步（仍不改代码，仅决策）

1. 评审本方案原则 **P0–P8** 与 tier 表是否采纳为平台契约（**P0 导入默认可用为产品底线**）  
2. 冻结 `aiplat.asset_compat.v1` 字段为跨模块接口  
3. 按 Phase A→D 排期；Phase A 必须先切断假绿 handler 默认启用，并落地 §5.4 启用确认  
4. 选定 4 个外源样例作为金样（含 mattpocock grill-me / grill-with-docs、一个 MCP server、一个 Hermes 风格 Agent 包）

---

## 18. 讨论修订记录（相对初稿）

| 议题 | 结论 | 方案是否已吸收 |
|------|------|:--------------:|
| 导入后要不要像 Cursor 一样马上能用？ | **要**；默认能用，不能用是例外 | ✅ §0.1b、P0、P3 |
| 审核会不会挡「第一次用」？ | **不应**；审核管上架/高权限 | ✅ §0.5、P3 |
| 没有 handler.py 能不能用？ | **能**；prompt 主路径不需要 | ✅ §5.3、§6.1 |
| 需要 handler 时是否自动生成并直接启用？ | **可生成草稿，默认不启用**；要人点「启用」 | ✅ §5.2、§5.4、P5 |
| 「确认」具体怎么做？ | 管理台升格页：看权限/差异 → 可选试跑 → 点启用并审计 | ✅ §5.4 |
| Agent 缺依赖是否完全不能用？ | **否**；对话默认能用，仅全功能受限 | ✅ §3.2 Agent、§6.2 |
| Tool「立刻能用」指什么？ | 映射成功或 MCP 投影成功后立刻可调；非任意 py 热加载 | ✅ §3.2 Tool、§6.3 |
| MCP 是否导入后立刻能用？ | 自动连接成功后默认能用；高风险工具可个别确认 | ✅ §3.2 MCP、§6.4 |
