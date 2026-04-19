# Packages Registry（P0 MVP）

本页描述 aiPlat-core 的 **Packages Registry**：将 “Agent + Skill + MCP + Hooks” 统一为可发布/可安装的版本化包，并接入审批与 autosmoke 验证。

## 1. 两类“包”的区别

### 1.1 Filesystem packages（定义层）

用于声明一个包包含哪些资源（不一定版本化）：

- Engine packages：`aiPlat-core/core/engine/packages/<name>/package.yaml`
- Workspace packages：`~/.aiplat/packages/<name>/package.yaml`

对应 core API（文件系统视角）：

- `GET  /api/core/workspace/packages?include_engine=true`
- `GET  /api/core/workspace/packages/{pkg_name}`
- `POST /api/core/workspace/packages/{pkg_name}/install`（按当前 filesystem 定义安装到 workspace）
- `POST /api/core/workspace/packages/{pkg_name}/uninstall`

### 1.2 Registry packages（发布层）

用于把某个 package **发布成不可变版本**（artifact + manifest），并可在不同时间反复安装该版本：

- 发布产物默认落在：`~/.aiplat/registry/packages/<pkg>/<version>.tar.gz`
- 元数据写入 ExecutionStore：
  - `package_versions`
  - `package_installs`

## 2. Registry API（版本化发布/安装）

### 2.1 发布版本

`POST /api/core/packages/{pkg_name}/publish`

请求体：

```json
{
  "version": "0.1.0",
  "require_approval": false,
  "approval_request_id": null,
  "details": "optional human readable"
}
```

说明：
- `require_approval=true` 且未提供 `approval_request_id` 时，会返回 `{status:"approval_required", approval_request_id:"..."}`，需要先走审批接口。

### 2.2 查看版本

- `GET /api/core/packages/{pkg_name}/versions`
- `GET /api/core/packages/{pkg_name}/versions/{version}`

### 2.3 安装版本

`POST /api/core/packages/{pkg_name}/install`

请求体：

```json
{
  "version": "0.1.0",
  "scope": "workspace",
  "allow_overwrite": false,
  "metadata": {"ticket":"ABC-123"},
  "require_approval": false,
  "approval_request_id": null,
  "details": "optional human readable"
}
```

说明：
- `version` 为空时：会回退为“按 filesystem package 当前定义安装”（等价于 `/workspace/packages/{pkg}/install`）
- 安装完成后会：
  1) 记录到 `package_installs`
  2) reload workspace managers + sync mcp runtime
  3) 对 agent/skill/mcp 标记 `metadata.verification.status=pending`
  4) 自动 enqueue autosmoke；完成后更新 `verified/failed`

### 2.4 查看安装记录

`GET /api/core/packages/installs?scope=workspace`

## 3. 审批接口（复用现有 ApprovalManager）

- `GET  /api/core/approvals/pending`
- `POST /api/core/approvals/{request_id}/approve`
- `POST /api/core/approvals/{request_id}/reject`

## 4. 示例：发布 + 安装 starter

1) 发布：

```bash
curl -X POST "$CORE/api/packages/starter/publish" \
  -H "Content-Type: application/json" \
  -d '{"version":"0.1.0"}'
```

2) 安装：

```bash
curl -X POST "$CORE/api/packages/starter/install" \
  -H "Content-Type: application/json" \
  -d '{"version":"0.1.0","allow_overwrite":false}'
```

3) 看 autosmoke / verification：
- `GET /api/diagnostics/e2e/smoke`（或管理台 Diagnostics）
- 资源 metadata.verification 字段

