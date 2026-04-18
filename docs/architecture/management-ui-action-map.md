# 管理画面按钮 → API → 状态/文件变更对照表（Agent / Skill / Tool / MCP）

> 目标：把管理端“点按钮会发生什么”说清楚：**调用哪个 API**、**改了什么状态**、**会不会写盘（哪些文件）**、以及 **engine vs workspace** 的差异。

---

## 0. 术语与 scope

- **engine（核心能力层）**
  - 资产目录：`aiPlat-core/core/engine/{agents,skills,mcps}`
  - API 前缀：`/api/core/*`
  - 策略：面向平台底座能力；通常 `protected: true`，**只允许启停/执行/查看**，禁止编辑/删除。

- **workspace（应用库/对外）**
  - 资产目录：`~/.aiplat/{agents,skills,mcps}`
  - API 前缀：`/api/core/workspace/*`
  - 策略：面向对外交付；允许创建/编辑/删除，但生产环境建议门控（白名单/审批/审计）。

> 注：对 **Tool** 来说，目前实现是“引擎代码注册”（非目录化资产），默认只读。

---

## 1. Agent 管理（核心能力层 / 应用库）

### 1.1 列表/刷新

- UI：刷新 / 首次进入页面
- API：
  - engine：`GET /api/core/agents?limit=&offset=&agent_type=&status=`
  - workspace：`GET /api/core/workspace/agents?limit=&offset=&agent_type=&status=`
- 变更：无（只读）

### 1.2 详情

- UI：点击 Agent 名称/详情按钮
- API：
  - engine：`GET /api/core/agents/{agent_id}`
  - workspace：`GET /api/core/workspace/agents/{agent_id}`
- 变更：无（只读）

### 1.3 创建（仅 workspace 建议启用）

- UI：创建 Agent
- API：
  - engine：`POST /api/core/agents`
  - workspace：`POST /api/core/workspace/agents`
- 变更：
  - engine：创建后写入 engine 管理平面数据（如启用目录写回，可能 materialize）
  - workspace：会写盘到 `~/.aiplat/agents/{agent_id}/AGENT.md`（目录化资产）

> 注意：workspace 不允许创建与 engine 同名（reserved_ids）。

### 1.4 编辑（config/skills/tools/metadata）

- UI：编辑
- API：
  - engine：`PUT /api/core/agents/{agent_id}`（若 `protected: true` → 403）
  - workspace：`PUT /api/core/workspace/agents/{agent_id}`
- 变更：
  - engine：更新运行态/管理态；`protected` agent 不允许编辑
  - workspace：更新运行态/管理态，并**最佳努力写回** `~/.aiplat/agents/{agent_id}/AGENT.md`

### 1.5 删除

- UI：删除
- API：
  - engine：`DELETE /api/core/agents/{agent_id}`（若 `protected: true` → 403）
  - workspace：`DELETE /api/core/workspace/agents/{agent_id}`
- 变更：
  - engine：从管理平面移除（保护 agent 禁止删除）
  - workspace：从管理平面移除（当前实现为内存删除；如需“删目录”，建议补 `delete_files=true` 模式与回收站策略）

### 1.6 启动/停止

- UI：启动 / 停止
- API：
  - engine：`POST /api/core/agents/{agent_id}/start`、`POST /api/core/agents/{agent_id}/stop`
  - workspace：`POST /api/core/workspace/agents/{agent_id}/start`、`POST /api/core/workspace/agents/{agent_id}/stop`
- 变更：修改 Agent `status`（运行态）

### 1.7 执行

- UI：执行
- API：
  - engine：`POST /api/core/agents/{agent_id}/execute`
  - workspace：`POST /api/core/workspace/agents/{agent_id}/execute`
- 变更：
  - 生成 execution 记录（ExecutionStore / traces）
  - 可能触发 skill/tool/mcp 调用（受白名单/审批/审计影响）

---

## 2. Skill 管理（核心能力层 / 应用库）

### 2.1 列表/刷新

- API：
  - engine：`GET /api/core/skills?limit=&offset=&category=&status=`
  - workspace：`GET /api/core/workspace/skills?limit=&offset=&category=&status=`
- 变更：无（只读）

### 2.2 详情

- API：
  - engine：`GET /api/core/skills/{skill_id}`
  - workspace：`GET /api/core/workspace/skills/{skill_id}`
- 变更：无（只读）

### 2.3 创建（建议仅 workspace）

- API：
  - engine：`POST /api/core/skills`
  - workspace：`POST /api/core/workspace/skills`
- 写盘：
  - workspace：`~/.aiplat/skills/{skill_id}/SKILL.md`
- 备注：workspace 不允许覆盖 engine 同名 skill（reserved_ids）。

### 2.4 编辑（name/description/config/metadata/schema）

- API：
  - engine：`PUT /api/core/skills/{skill_id}`（若 `protected: true` → 403）
  - workspace：`PUT /api/core/workspace/skills/{skill_id}`
- 写盘：
  - workspace：最佳努力写回 `~/.aiplat/skills/{skill_id}/SKILL.md`（保留 SOP 正文）

### 2.5 启用/禁用/恢复

- API：
  - engine：`POST /api/core/skills/{skill_id}/enable|disable|restore`
  - workspace：`POST /api/core/workspace/skills/{skill_id}/enable|disable|restore`
- 变更：
  - 修改 skill `status`（enabled/disabled/deprecated）
  - 同步执行层 SkillRegistry（best-effort）

### 2.6 弃用（soft delete）/ 彻底删除（hard delete）

- UI：弃用（soft） / 彻底删除（hard）
- API：
  - engine：`DELETE /api/core/skills/{skill_id}`（可带 `?delete_files=true`；protected 403）
  - workspace：`DELETE /api/core/workspace/skills/{skill_id}`（可带 `?delete_files=true`）
- 写盘：
  - soft delete：保留目录，仅在 `SKILL.md` frontmatter 标记 deprecated + deprecated_at
  - hard delete：删除 `~/.aiplat/skills/{skill_id}` 目录（谨慎）

### 2.7 执行

- API：
  - engine：`POST /api/core/skills/{skill_id}/execute`
  - workspace：`POST /api/core/workspace/skills/{skill_id}/execute`
- 变更：生成 execution 记录，可能触发 tool/mcp 调用

### 2.8 版本/回滚/执行记录/绑定关系（workspace 更常用）

- 版本与回滚：
  - `GET /api/core/workspace/skills/{skill_id}/versions`
  - `GET /api/core/workspace/skills/{skill_id}/active-version`
  - `POST /api/core/workspace/skills/{skill_id}/versions/{version}/rollback`
- 执行记录：`GET /api/core/workspace/skills/{skill_id}/executions`
- 被哪些 agent 绑定：`GET /api/core/workspace/skills/{skill_id}/agents`

---

## 3. Tool 管理（核心能力层）

> Tool 当前属于“执行层注册的代码能力”（非目录化资产），因此管理面主要做 **查看/执行/统计**，不支持编辑。

### 3.1 列表/详情

- API：`GET /api/core/tools`、`GET /api/core/tools/{tool_name}`
- 变更：无（只读）

### 3.2 执行

- API：`POST /api/core/tools/{tool_name}/execute`
- 变更：生成执行记录（ExecutionStore / traces），并更新 tool stats

### 3.3 编辑配置（已禁用）

- API：`PUT /api/core/tools/{tool_name}` → **403**
- 说明：避免在 UI 中修改引擎工具行为，配置应走代码/配置文件/feature flags。

---

## 4. MCP 管理（核心能力层 / 应用库）

### 4.1 列表/刷新

- API：
  - engine：`GET /api/core/mcp/servers`
  - workspace：`GET /api/core/workspace/mcp/servers`
- 变更：无（只读）

### 4.2 启用/禁用

- API：
  - engine：`POST /api/core/mcp/servers/{name}/enable|disable`
  - workspace：`POST /api/core/workspace/mcp/servers/{name}/enable|disable`
- 写盘（目录化配置）：
  - `~/.aiplat/mcps/{name}/server.yaml`（enabled 字段变更）
  - `~/.aiplat/mcps/{name}/policy.yaml`（allowed_tools）

### 4.3 详情

- UI：详情弹窗（可复制 server.yaml/policy.yaml 路径）
- API：来自列表数据（无需额外接口）
- 变更：无（只读）

---

## 5. 关键约束（建议固化为产品规则）

1. **engine + protected**：只允许“启停/执行/查看/版本回滚（如有）”，禁止编辑/删除。
2. workspace：允许 CRUD，但生产环境建议：
   - 默认禁用高风险能力（browser / api_calling / tool_agent）
   - 白名单 + 审批 + 审计
3. 目录化资产的“写回”是 best-effort：以文件为真值源，UI 修改应当尽量保持 SOP 正文不被覆盖。

