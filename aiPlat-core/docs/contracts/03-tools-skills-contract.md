# Tools & Skills Contract（工具/技能契约）

本文件约束 Tool/Skill 的“可发现、可治理、可观测、可验收”。

## 1. 基本定义（MUST）

- **Tool**：外部接口能力（执行副作用或访问外部资源），必须受 policy/approval 约束。  
- **Skill**：内部能力（通常纯计算/封装流程），也可以受约束，但默认风险更低。

### 1.1 Skill 类型（MUST）

为对齐 OpenCode/Claude Code 的使用习惯，并避免“只有 SKILL.md 是否等同可执行能力”的歧义，系统 **MUST** 区分两种 Skill：

- **规则型 Skill（Rule Skill）**：以 `SKILL.md/CLAUDE.md` 为载体的 SOP/行为规范/模板。  
  - **不新增可执行能力**；仅用于 prompt 注入与工作流约束。
- **可执行型 Skill（Executable Skill）**：包含可执行入口（代码/manifest/handler），可被 Harness 调用执行（走 `sys_skill_call`）。

> 自动判别规则与生产安全门槛由 `07-skill-types-contract.md` 定义。

## 2. Schema 与稳定命名（MUST）

每个 tool/skill **MUST**：
- 有稳定 `name`
- 有清晰 `description`
- 有参数 `schema`（JSON Schema / Pydantic 等），包含 required/类型/约束

工具名 **MUST** 全局唯一，避免同名覆盖导致不可预期行为。

## 3. 动态发现（tool_search）（MUST）

当工具规模较大（尤其 MCP 工具多）时，系统 **MUST** 支持按需发现：
- 必须存在 `tool_search` 工具，用于按 `query/name/category` 搜索工具并返回截断版 schema
- 当工具描述被预算截断时，`tool_search` **MUST** 仍对模型可见（防止“看不到工具但又需要工具”）

## 4. 工具描述预算（MUST）

为了避免每轮把全量工具 schema 倾倒进 prompt，系统必须支持预算控制：
- 单工具描述最大字符数：`AIPLAT_TOOL_DESC_PER_TOOL_MAX_CHARS`
- 全体工具描述最大字符数：`AIPLAT_TOOLS_DESC_MAX_CHARS`

当发生截断/隐藏时：
- **MUST** 在可观测事件中记录：included/hidden/truncated/chars_total
- **SHOULD** 在工具描述尾部提示“使用 tool_search”

## 5. Skills 发现与按需加载（find/load）（MUST）

为避免“把所有 skills 内容常驻 prompt”导致 prompt bloat，系统 **MUST** 支持 skills 的“索引发现 + 按需加载”：

- **MUST** 提供 `skill_find`：按 `query/name/kind/category` 返回 skills 摘要列表（仅 name/description/metadata，禁止返回全文）。
- **MUST** 提供 `skill_load`：按 `name` 加载规则型 Skill 的 SOP 正文，并以可控方式注入到 prompt（推荐 overlay 注入，同时记录 hash/version）。
- **SHOULD** 支持 `skill_info`：查看技能元数据（含 provenance/integrity/permissions）。

### 5.1 Skills 列表预算（MUST）

系统向模型暴露 “可用 skills 列表”时 **MUST** 受预算控制（类似 tools desc budget）：
- 单 skill 描述最大字符数：`AIPLAT_SKILL_DESC_PER_SKILL_MAX_CHARS`
- 全体 skills 列表最大字符数：`AIPLAT_SKILLS_DESC_MAX_CHARS`

当发生截断/隐藏时：
- **MUST** 在可观测事件中记录：included/hidden/truncated/chars_total
- **SHOULD** 提示“使用 skill_find 缩小范围”

## 6. 权限/审批/策略（MUST）

工具调用 **MUST** 经过（至少一种）治理路径：
- PolicyGate（策略判定 allow/deny + 原因）
- ApprovalGate（需要人工批准时可暂停/恢复）

工具本身 **SHOULD** 声明风险等级（risk_level/risk_weight），用于审批与审计分级。

### 6.1 Skills 权限（MUST）

系统 **MUST** 对 skills 的加载/执行施加权限控制（支持通配符），并至少支持三态：
- `allow`：允许 load/execute
- `ask`：触发 ApprovalGate（生产推荐默认）
- `deny`：隐藏或拒绝

权限至少覆盖：
- `skill_find`（通常 allow）
- `skill_load`（规则型 skill 的正文注入）
- `skill_execute`（可执行型 skill 的实际执行）

## 7. 观测与审计（MUST）

每次 tool/skill 调用 **MUST** 可追溯：
- trace_id/run_id
- tool_name/skill_name + args（可脱敏/截断）
- outcome（ok/error_code/latency）
- policy/approval 结果（如果发生）

对于规则型 skill 的注入，至少记录：
- skill_name、skill_hash（或 version）
- 注入模式（stable/overlay）

## 8. Exec Backends（SHOULD）

代码执行类工具（如 `code`）**SHOULD** 通过 ExecDriver 抽象后端：
- 支持 `local/docker/ssh...`
- health 输出结构一致
- capabilities（能力矩阵）可用于诊断与路由决策
