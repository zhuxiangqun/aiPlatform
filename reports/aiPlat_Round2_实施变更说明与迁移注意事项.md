# aiPlat Round2 实施变更说明与迁移注意事项

更新时间：2026-04-15  
适用范围：`aiPlat-core`（含 Harness / Agent / Skill / Tool 运行时与 API）

> 本文用于运维与开发快速理解 Round2 落地后的“新接口/新默认行为/兼容性注意事项”。  
> Round2 复审报告与审查项见：`reports/aiPlat_设计文档与实现一致性复审_Round2.docx`、`reports/audit_findings_round2.json`。
>
> **历史报告**：本文为 Round2 时点的迁移说明快照；当前实现与默认行为以最新代码与测试为准。

---

## 1. 权限体系（R2-AUTH-001）

### 1.1 默认行为变化

为避免“开箱即 403”，服务启动时会默认 **seed** `system,admin` 对所有已注册 **agent/skill/tool** 的 `EXECUTE` 权限。

可通过环境变量关闭或调整：
- `AIPLAT_SEED_DEFAULT_PERMISSIONS=false`：关闭默认 seed
- `AIPLAT_DEFAULT_PERMISSION_USERS=system,admin`：调整默认 seed 的用户列表（逗号分隔）

> 注意：关闭 seed 后，若未通过权限 API 手动授权，`execute_agent/execute_skill` 可能返回 403（符合 deny-by-default）。

### 1.2 新增权限管理 API

路由前缀：`/api/core`

- `GET  /permissions/stats`：统计信息
- `GET  /permissions/users/{user_id}`：查询某用户的授权集合
- `GET  /permissions/resources/{resource_id}`：查询某资源（tool/skill/agent 名称）被哪些用户授权
- `POST /permissions/grant`：授权
- `POST /permissions/revoke`：撤销授权

#### grant 示例
```json
POST /api/core/permissions/grant
{
  "user_id": "u1",
  "resource_id": "calculator",
  "permission": "execute",
  "granted_by": "admin"
}
```

#### revoke 示例（撤销该用户对该资源的全部权限）
```json
POST /api/core/permissions/revoke
{
  "user_id": "u1",
  "resource_id": "calculator"
}
```

---

## 2. Skill 版本回滚语义（R2-SKILL-VERSION-SEM-001）

### 2.1 行为语义变化

`SkillRegistry.rollback_version(name, version)` 不再仅切换 `is_active`，而是会将目标版本的 `SkillConfig` **应用到当前 skill 实例**（更新其 `_config`），确保回滚对后续执行“可见”。

新增能力：
- `SkillRegistry.get_active_version(name)`：查询当前生效版本

### 2.2 API 行为变化

路由前缀：`/api/core`

- `POST /skills/{skill_id}/versions/{version}/rollback`
  - 现在会校验版本是否存在；不存在返回 `404`
  - 成功时返回 `active_version` 与 `active_config`
- `GET  /skills/{skill_id}/active-version`
  - 返回当前 `active_version`

---

## 3. Harness Hook 治理接线（R2-HOOK-SEC-001）

### 3.1 执行路径中的新增 HookPhase

已在 Loop 主执行路径接入并触发：
- `SESSION_START` / `SESSION_END`
- `PRE_CONTRACT_CHECK` / `POST_CONTRACT_CHECK`
- `STOP`

在工具调用前后接入：
- `PRE_APPROVAL_CHECK` / `POST_APPROVAL_CHECK`
  - 支持 hook 返回 `{"allow": false, "reason": "..."}` 直接阻断本次工具调用（返回 `Denied: ...`）

### 3.2 默认 Hook（最小安全基线）

`HookManager()` 构造时会默认注册 `get_default_hooks()` 返回的 hooks，包括：
- session_start/session_end（轻量）
- pre_approval_check：基于 `SecurityScanHook` 的敏感信息扫描（当前对 Write/Edit 输入进行扫描）

> 注意：当前默认安全扫描属于“最小基线”，后续如需更严格审批或合约校验，应通过自定义 hook 注册完成。

---

## 4. 观测驱动控制（R2-OBS-CONTROL-001）

### 4.1 最小闭环已落地（Loop 内置）

ReActLoop 在工具执行时记录：
- `state.metadata.tool_calls`
- `state.metadata.tool_failures`

BaseLoop 在每步后应用最小控制规则：
- 若 `tool_error_rate > 0.2` 且 `tool_calls >= 10`：将 Loop 置为 `PAUSED`，并写入：
  - `state.metadata.control_action=require_manual`
  - `state.context.observation` 提示暂停原因
- 若 token 使用占比 > 0.8（best-effort）：压缩 `state.context.messages`（保留末 2 条）

> 注意：这是“最小闭环实现”，并非完整的 PolicyEngine；后续可演进为可配置策略与更丰富动作。

---

## 5. Tool 线程安全与可选 tracing（R2-TOOL-THREADSAFE-001）

### 5.1 线程安全最小集

- `BaseTool` stats 更新已加锁（避免并发更新导致统计不一致）
- `ToolRegistry` 对注册/查询/统计等操作加入 `RLock`

### 5.2 tracer span（可选）

若注入 tracer（具备 `start_span(name)`），`BaseTool._call_with_tracking()` 会在调用 handler 时创建 span。  
兼容 tracer 返回 sync/async context manager（`__enter__`/`__aenter__`）。

---

## 6. Agent 状态模型收敛（R2-AGENT-STATE-001）

### 6.1 Canonical 状态来源

以 `core.harness.state.AgentStateEnum` 作为 canonical（created/initializing/ready/running/paused/stopped/error/terminated）。

### 6.2 关键收敛点

- `core.management.AgentManager`：
  - seed 数据与 start/stop、create_agent 的 status 输出改为 canonical 值
  - 增加 `_normalize_status()` 以兼容历史字符串
- execution-layer `AgentRegistry`：
  - 默认状态由 `idle` 调整为 `ready`

---

## 7. 建议的运维/发布检查项

1) 启动后检查默认权限 seed 是否符合预期  
   - 如希望严格默认拒绝：设置 `AIPLAT_SEED_DEFAULT_PERMISSIONS=false`，并通过 permissions API 授权
2) 回滚能力抽样验证  
   - rollback 后查询 `/active-version` 与执行结果应反映目标版本
3) Hook 阻断链路验证  
   - 构造含 `sk-...` 的 Write/Edit 输入，预期触发 `Denied:`（最小安全基线）
