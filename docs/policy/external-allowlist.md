# 对外能力白名单（Engine vs Workspace）

> 目标：在 **workspace（对外/应用库）默认拒绝** 的前提下，明确哪些 **engine（核心能力层）** 的能力允许“对外可用”（按 dev / staging / prod 区分）。

## 1. 基本定义

### 1.1 scope

- **engine（核心能力层专用）**
  - 定义目录：`aiPlat-core/core/engine/{agents,skills,mcps}`
  - 管理入口：管理端侧边栏「核心能力层」→ `/core/*`
  - API：`/api/core/{agents,skills,mcp/*}`

- **workspace（对外/应用库）**
  - 定义目录：`~/.aiplat/{agents,skills,mcps}`
  - 管理入口：管理端侧边栏「应用库」→ `/workspace/*`
  - API：`/api/core/workspace/*`

### 1.2 对外可用（External-facing）的含义

在本白名单中，“对外可用”主要指：
1. **允许 workspace 侧被绑定/被调用**（例如 workspace agent 绑定某个 engine skill / tool / mcp server）。
2. **允许在管理端‘应用库’中展示/启用相应能力**（避免把 engine 的内部能力误暴露给外部用户）。

> 说明：执行控制权始终由 core Harness/Runtime 统一控制；白名单只决定“是否允许对外调用/启用”。

## 2. 默认策略（Recommended）

### 2.1 默认拒绝

- workspace **默认不允许**使用任何 engine 的：
  - Agent（engine agents）
  - Skill（engine skills）
  - MCP server（engine mcps）
- 必须通过本白名单显式允许（按环境）。

### 2.2 分级原则

| 级别 | 定义 | 建议环境 |
|------|------|----------|
| L0 | 纯文本/无外部副作用（翻译/总结/闲聊等） | dev / staging / prod |
| L1 | 只读检索（不触发外部写操作） | dev / staging / prod（建议加审计） |
| L2 | 可能触发外部交互/系统调用（浏览器、工具链等） | dev / staging（建议审批） |
| L3 | 高风险写操作/执行（生产环境变更等） | 仅 dev（或完全禁用） |

## 3. 白名单清单（按环境）

> 本表只列“允许对外使用的 engine 能力”。  
> workspace 自己创建的能力（`~/.aiplat/*`）默认属于对外能力，但仍建议在 prod 走审批/审计。

### 3.1 Engine Skills（核心能力层内置 Skill）

| engine skill_id | 风险级别 | dev | staging | prod | 备注 |
|---|---:|:---:|:---:|:---:|---|
| `translation` | L0 | ✅ | ✅ | ✅ | 翻译（低风险） |
| `summarization` | L0 | ✅ | ✅ | ✅ | 总结（低风险） |
| `knowledge_retrieval` | L1 | ✅ | ✅ | ✅ | 检索增强（建议加审计） |
| `task_planning` | L0 | ✅ | ✅ | ✅ | 规划（不含执行） |
| `task_decomposition` | L0 | ✅ | ✅ | ✅ | 分解（不含执行） |
| `text_generation` | L0 | ✅ | ✅ | ✅ | 文本生成（内容安全另行约束） |

### 3.1.1 Workspace 默认技能（seeds）

> 下列能力不再作为 engine 内置能力对外暴露，而是以 **workspace seeds** 形式提供默认模板：  
> core 启动时会将其（若不存在）materialize 到 `~/.aiplat/skills/*`，由应用库自行启用/配置，并按环境走白名单/审批。

| workspace skill_id | 风险级别 | dev | staging | prod | 默认状态 | 备注 |
|---|---:|:---:|:---:|:---:|:---:|---|
| `chitchat` | L0 | ✅ | ✅ | ✅ | enabled | 闲聊/引导（对外体验能力） |
| `data_analysis` | L1 | ✅ | ✅ | ✅ | enabled | 数据需合规（建议脱敏） |
| `code_review` | L1 | ✅ | ✅ | ✅ | enabled | 注意代码/日志脱敏与权限隔离 |
| `information_search` | L1 | ✅ | ✅ | ⚠️ | disabled | prod 建议只走受控数据源 |
| `code_generation` | L1 | ✅ | ✅ | ⚠️ | disabled | prod 需配套代码安全策略 |
| `api_calling` | L2 | ✅ | ✅ | ❌ | disabled | 外部 API 调用，prod 默认禁用或强审批 |

### 3.2 Engine Agents（核心能力层内置 Agent）

| engine agent_id | 风险级别 | dev | staging | prod | 备注 |
|---|---:|:---:|:---:|:---:|---|
| `conversational_agent` | L0 | ✅ | ✅ | ✅ | 对话型（低风险） |
| `rag_agent` | L1 | ✅ | ✅ | ✅ | 依赖知识库合规与权限 |
| `react_agent` | L2 | ✅ | ✅ | ❌ | 具备工具编排倾向，prod 默认不对外 |
| `plan_agent` | L1 | ✅ | ✅ | ⚠️ | prod 可用但建议仅“规划输出”，不自动执行 |
| `tool_agent` | L2 | ✅ | ✅ | ❌ | 工具优先，prod 默认不对外 |

### 3.3 Engine MCP Servers（核心能力层内置 MCP）

| engine mcp server | 风险级别 | dev | staging | prod | 备注 |
|---|---:|:---:|:---:|:---:|---|
| `integrated_browser` | L2 | ✅ | ✅ | ❌ | 浏览器自动化：强建议审批+审计，prod 默认禁用 |

## 4. 推荐的对外暴露方式（实现建议）

1. **对外只通过 workspace 管理入口使用能力**：即用户只接触 `/workspace/*` 菜单与 `/api/core/workspace/*` API。
2. **若需对外提供 engine 能力**：优先在 workspace 创建“封装”版本（workspace skill/agent），并在封装内显式调用被允许的 engine skill/tool/mcp（受本白名单约束）。
3. **生产环境（prod）必备**：
   - 审计：记录调用链、输入输出摘要、耗时、失败原因
   - 审批：对 L2/L3 类能力启用审批（尤其是 MCP/browser、api_calling 等）
   - 内容/数据安全：脱敏、权限校验、DLP（如需要）

## 5. 变更流程（建议）

1. 任何白名单变更必须带：
   - 变更原因（risk/benefit）
   - 回滚方案
   - 影响面（哪些 workspace app / agent 会受影响）
2. prod 白名单调整建议走评审与灰度。
