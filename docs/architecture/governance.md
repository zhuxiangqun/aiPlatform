# aiPlat 治理体系

## 1 治理是什么

> 治理 = **签名 + 权限 + 审批**，贯穿实体从"创建"到"退役"全生命周期。

```
签名  → 证明"这代码没被改过"（Ed25519 非对称加密）
权限  → 控制"谁能调用它"（RBAC 基于角色的访问控制）
审批  → 确保"高风险操作有人盯着"（人工或自动审核）
```

### 1.1 为什么需要治理

**治理前**（系统中 47 个 Skill 的实际状态）：

```
0 个有签名（provenance.signature 全部为空）
0 个经过 Ed25519 验签
0 个执行过 RBAC 权限检查
0 个创建过审批请求
```

**治理后**，每一个实体的创建/更新/启用/执行/退役都有自动化的安全边界。

### 1.2 治理覆盖矩阵

| 实体 | 目录存储 | manifest | 签名端点 | 验签(Ops) | 发布门禁 | PolicyGate | 前端签名UI |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **Skills** | ✅ | ✅ | ✅ | ✅ | ✅ | `check_skill()` | ✅ |
| **Agents** | ✅ | ✅ | ✅ | ✅ | ✅ | `check_agent()` | ✅ |
| **MCP** | ✅ | ✅ | ✅ | ✅ | ✅ | prod_policy | ✅ |
| **Tools** | ✅ | ✅ | ✅ | ✅ | ✅ | `check_tool()` | ✅ |
| **Workflows** | ✅ | ✅ | ✅ | ✅ | ✅ | `check_workflow()` | ✅ |
| **Builder** | ✅ | ✅ | ✅ | ✅ | ✅ | start_pipeline 验签 | ✅ |
| **Prompt Apps** | ✅ | ✅ | ✅ | ✅ | ✅ | publish 验签 | ✅ |

所有 7 个实体类型使用**完全相同的治理基础设施**：
- 相同的 Ed25519 签名密码学（`crypto/signature.py`）
- 相同的 bundle_sha256 完整性校验
- 相同的 manifest.json 溯源格式
- 相同的 RBAC 权限框架（`PolicyGate`）
- 相同的 approval 审批流
- 相同的前端签名 UI 模式（粘贴私钥 PEM → 签名）

---

## 2 治理架构

### 2.1 实体存储模型

所有被治理的实体都使用**统一的目录化存储**：

```
~/.aiplat/
├── skills/<id>/
│   ├── SKILL.md              │ 实体定义
│   ├── SKILL.manifest.json   │ 溯源签名
│   └── scripts/              │ 附属资源
├── agents/<id>/
│   ├── AGENT.md
│   ├── AGENT.manifest.json
│   └── ...
├── mcps/<id>/
│   ├── server.yaml
│   ├── policy.yaml
│   └── MCP.manifest.json
├── workflows/<id>/
│   ├── workflow.json
│   └── WORKFLOW.manifest.json
├── projects/<id>/
│   ├── project.json
│   └── PROJECT.manifest.json
├── prompt-apps/<id>/
│   ├── template.json
│   └── TEMPLATE.manifest.json
└── tools/<name>.py
    └── <name>.TOOL.manifest.json
```

`manifest.json` 统一格式：

```json
{
  "publisher": "acme",
  "source": "https://github.com/acme/skills",
  "version": "1.2.3",
  "signature": "base64:..."
}
```

### 2.2 密码学基础设施

所有实体的签名/验签共用 `aiPlat-core/core/harness/infrastructure/crypto/signature.py`：

```
generate_ed25519_key_pair()  → 生成密钥对（PEM 格式）
sign_skill(id, version, bundle_sha256, private_key)  → Ed25519 签名
verify_skill_signature(id, version, bundle_sha256, signature, trusted_keys)  → 验签
canonical_skill_payload(id, version, bundle_sha256)  → 规范化载荷
key_id_for_public_key(public_key)  → 公钥 ID
```

签名流程：`payload = {id, version, bundle_sha256} → JSON 排序序列化 → SHA256 → Ed25519.sign() → base64`

### 2.3 密钥生命周期

```
1. 生成密钥对
   POST /onboarding/generate-skill-key
   → 服务端生成 Ed25519 密钥对
   → 私钥返回给用户（一次性展示，不存储）
   → 公钥自动写入 trusted_skill_pubkeys

2. 签名实体
   POST /{entity}/{id}/sign  {private_key: "-----BEGIN PRIVATE KEY-----..."}
   → 计算 bundle_sha256
   → Ed25519.sign(payload)
   → 写入 manifest.json

3. 验签
   每次 enable/execute/publish 时自动触发
   → 读 manifest.json → 获取签名
   → 计算当前 bundle_sha256 → 对比
   → verify_skill_signature() → 返回 verified/not_verified
```

### 2.4 PolicyGate（单次执行点）

`aiPlat-core/core/harness/infrastructure/gates/policy_gate.py` 是所有执行路径的**唯一**权限+审批检查点。

```
PolicyGate
├── check_skill()     → sys_skill_call() 入口
├── check_tool()      → sys_tool_call() 入口
├── check_agent()     → agent_execute() 入口
└── check_workflow()  → workflow_execute() 入口

每个 check_*() 执行相同的流程：
  1. RBAC 权限检查 → deny 无 EXECUTE 权限
  2. 审批采样策略 → always/sample/risk_sample/never
  3. 审批请求 → PENDING(暂停) / APPROVED(放行) / REJECTED(拒绝)
```

**架构原则**：同一请求对同一资源的权限检查，整个调用链中**只执行一次**，PolicyGate 是唯一执行点。上游层（HTTP Gateway）只做身份注入，不做权限判断。

---

## 3 治理时机与流程

### 3.1 完整生命周期

```
时间点                        | 触发事件                | 治理动作
──────────────────────────────┼────────────────────────┼────────────────────
CREATE                        | create()                | bundle_sha256 计算
                              |                         | provenance 写入
                              |                         | integrity enrichment
──────────────────────────────┼────────────────────────┼────────────────────
UPDATE                        | update()                | autosmoke 重新排队
                              |                         | provenance 刷新
──────────────────────────────┼────────────────────────┼────────────────────
SUBMIT-FOR-REVIEW             | submit_for_review()     | Lint Gate 检查
                              |                         | governance → "pending"
──────────────────────────────┼────────────────────────┼────────────────────
SIGN                          | POST /{entity}/{id}/sign| Ed25519 签名
                              | (用户粘贴私钥)          | manifest.json 写入
──────────────────────────────┼────────────────────────┼────────────────────
ENABLE                        | enable() 三道闸         | 1. Autosmoke enforce
                              |                         | 2. Lint Gate
                              |                         | 3. Signature Gate
──────────────────────────────┼────────────────────────┼────────────────────
EXECUTE                       | sys_*_call()            | PolicyGate RBAC + Approval
                              |                         | Signature verify (Ops)
──────────────────────────────┼────────────────────────┼────────────────────
PUBLISH/DEPLOY                | publish / deploy-to-app | 签名验证 → 403 拒绝
                              |                         | changeset 记录
──────────────────────────────┼────────────────────────┼────────────────────
DEPRECATE                     | delete(soft=True)       | status → deprecated
                              |                         | deprecated_at 时间戳
──────────────────────────────┼────────────────────────┼────────────────────
CRON (持续)                   | SkillCurator            | 30d stale → 90d archived
                              | skill_lint_scan Job     | 全量巡检 + 告警
```

### 3.2 治理 vs 预治理

| 维度 | 已治理（有签名） | 预治理（无签名） |
|------|----------------|-----------------|
| 签名验证 | ✅ Ed25519 验签 | ❌ 跳过 |
| 权限声明 | ✅ 必须声明 `permissions` | ❌ 免检 |
| 执行审批 | 全流程 PolicyGate | 跳过权限+签名闸 |
| Lint | 全量规则 | 全量规则 |
| 设计意图 | 生产级安全 | 开发/实验阶段免摩擦 |

判断逻辑：`signature_gate_eval()` 检查 `provenance.signature`
- 为空 → `required: false, reason: "pre_governance_no_signature"`
- 有值 → 调用 `verify_skill_signature()` 验签

### 3.3 Enable 三道闸（关键路径）

以 **Skill** 的 enable 流程为例（`workspace_skills.py:1297-1517`）：

```
enable_skill(skill_id)
  │
  ├── 1. Autosmoke Gate
  │      autosmoke_enforce() → 冒烟测试通过?
  │      ❌ fail → 409 拒绝
  │      ✅ pass → 继续
  │
  ├── 2. Lint Gate
  │      lint_skill() → lint_summary.blocked?
  │      ✅ blocked && risk=high → 409 "skill_lint_blocked"
  │      ❌ ok → 继续
  │
  ├── 3. Signature Gate
  │      compute_skill_signature_verification()
  │      ↓
  │      signature_gate_eval(metadata, trusted_keys_count)
  │      ├─ 无签名 → pre_governance 豁免
  │      ├─ 验签通过 → 放行
  │      ├─ 验签失败 → require_approval()
  │      │    ├─ PENDING → 409 "not_approved"（等待管理员）
  │      │    └─ APPROVED → 继续
  │      └─ 无可信公钥 → require_approval()
  │
  └── 4. enable_skill() → status = "enabled"
        record_changeset()
        add_audit_log()
```

**Agent、MCP、Workflows、Prompt Apps** 遵循相同或简化的模式——核心差异仅在于触发时机和严格程度不同。

### 3.4 运行时执行路径

```
sys_skill_call() / sys_tool_call()
  │
  ├── TraceGate.start()  → span
  │
  ├── 权限解析
  │     resolve_skill_permission() / resolve_executable_skill_permission()
  │     ├─ "deny"  → 直接拒绝
  │     ├─ "ask"   → _approval_required = true
  │     └─ "allow" → 继续
  │
  ├── 预治理豁免（无签名 skill）
  │     has_sig = bool(prov.get("signature"))
  │     if not has_sig: require_perm = False
  │
  ├── PolicyGate.check_skill() / check_tool()
  │     ├─ RBAC: perm_mgr.check_permission(user_id, name, EXECUTE)
  │     ├─ Approve 采样: _maybe_waive_approval(mode, rate)
  │     └─ 审批请求: approval_mgr.check_and_request(ctx)
  │          ├─ PENDING → APPROVAL_REQUIRED（循环暂停）
  │          ├─ APPROVED → ALLOW
  │          └─ REJECTED → DENY
  │
  └── execute skill/tool → 结果
        → add_audit_log()
```

---

## 4 各实体治理详解

### 4.1 Skills

| 维度 | 文件 | 关键函数 |
|------|------|---------|
| 溯源码 | `skill_manager.py:381-412` | `_enrich_skill_provenance_and_integrity()` |
| 完整性 | `skill_manager.py:339-378` | `_compute_skill_bundle_integrity()` |
| 签名 | `workspace_skills.py:1518+` | `POST /skills/{id}/sign` |
| 验签 | `skill_manager.py:414-448` | `compute_skill_signature_verification()` |
| 启用门禁 | `workspace_skills.py:1297-1517` | `enable_workspace_skill()` 三道闸 |
| 执行门禁 | `syscalls/skill.py:424-449` | `PolicyGate.check_skill()` |
| Lint | `skill_linter.py` + `lint_rules/` | 20 条声明式规则 + 3 条治理规则 |
| 策展 | `curator.py` | 30d stale → 90d archived |
| 前端 | `Skills.tsx` | 详情弹窗：粘贴密钥 + 签名按钮 |

### 4.2 Agents

| 维度 | 文件 | 关键函数 |
|------|------|---------|
| 溯源码 | `agent_manager.py:284-350` | `_enrich_agent_provenance_and_integrity()` |
| 完整性 | `agent_manager.py:300-320` | `_compute_agent_bundle_integrity()` |
| 签名 | `workspace_agents.py:1115+` | `POST /agents/{id}/sign` |
| 验签 | `agent_manager.py:352-375` | `compute_agent_signature_verification()` |
| 启用门禁 | `workspace_agents.py:1178+` | `enable_workspace_agent()` 三道闸 |
| 执行门禁 | `policy_gate.py:646+` | `PolicyGate.check_agent()` |
| 前端 | `AgentDetailModal.tsx` | 粘贴密钥 + 签名按钮 |

### 4.3 MCP

| 维度 | 文件 | 关键函数 |
|------|------|---------|
| 溯源码 | `mcp_manager.py:153-245` | `_enrich_mcp_provenance_and_integrity()` |
| 签名 | `mcp_admin.py:186+` | `POST /mcp/servers/{name}/sign` |
| 验签 | `mcp_manager.py:245-274` | `compute_mcp_signature_verification()` |
| 启用门禁 | `mcp_admin.py:100-139` | `enable_mcp_server()` autosmoke + change-control |
| 生产策略 | `prod_policy.py` | `prod_stdio_policy_check()` |
| 前端 | `MCP.tsx` | 详情弹窗：粘贴密钥 + 签名按钮 |

### 4.4 Tools

| 维度 | 文件 | 关键函数 |
|------|------|---------|
| 溯源码 | `discovery.py:60-155` | `_read_tool_manifest()` + `_sha256_file()` |
| 签名 | `tools.py:200+` | `POST /tools/{name}/sign` |
| 验签 | `discovery.py:24-36` | `_verify_tool_signature()` |
| 执行门禁 | `syscalls/tool.py:394-405` | `PolicyGate.check_tool()` |
| 前端 | `ToolDetailModal.tsx` | 粘贴密钥 + 签名按钮 |

### 4.5 Workflows

| 维度 | 文件 | 关键函数 |
|------|------|---------|
| 溯源码 | `workflow_manager.py:215-275` | `_enrich_workflow_provenance_and_integrity()` |
| 签名 | `workflows.py:162+` | `POST /workflows/{id}/sign` |
| 验签 | `builder_workflow_service.py:47-60` | `_verify_workflow_signature()` |
| 执行门禁 | `policy_gate.py:720+` | `PolicyGate.check_workflow()` |
| 审计 | `workflows.py:45-55` | `_record_workflow_changeset()` (5 个操作) |
| 前端 | `WorkflowsPage.tsx` | 详情弹窗（Info 图标）：粘贴密钥 + 签名按钮 |

### 4.6 Builder Projects

| 维度 | 文件 | 关键函数 |
|------|------|---------|
| 签名字段 | `builder_project_service.py:193-210` | `_save_projects()` 自动读写 `PROJECT.manifest.json` |
| 验签 | `builder_project_service.py:770+` | `start_pipeline` 前置验签 |
| 部署门禁 | `builder.py:202+` | `deploy-to-app` 签名失败 → 403 |
| 审计 | `builder_project_service.py:760-772` | `start_pipeline` 自动记录 changeset |

### 4.7 Prompt Apps

| 维度 | 文件 | 关键函数 |
|------|------|---------|
| 溯源码 | `prompt_app_manager.py:195-215` | `_enrich_provenance_and_integrity()` |
| 签名 | `prompt_app.py:625+` | `POST /templates/{id}/sign` |
| 验签 | `prompt_app.py:65-78` | `_verify_template_signature()` |
| 发布门禁 | `prompt_app.py:147+` | `publish_template()` 签名失败 → 403 |
| 审计 | `prompt_app.py:42-54` | `_record_changeset()` (create/update/delete) |
| 前端 | `AppTemplates.tsx` | 操作栏 Key 按钮 → 签名弹窗 |

---

## 5 可用 API

### 5.1 密钥管理

```
POST /onboarding/generate-skill-key        → 生成 Ed25519 密钥对
POST /onboarding/trusted-skill-keys        → 上传可信公钥列表
```

### 5.2 签名

```
POST /workspace/skills/{id}/sign           → Skill 签名
POST /workspace/agents/{id}/sign           → Agent 签名
POST /mcp/servers/{name}/sign              → MCP 签名
POST /tools/{name}/sign                    → 工具签名
POST /platform/workflows/{id}/sign         → Workflow 签名
POST /platform/builder/projects/{id}/sign  → Builder 项目签名
POST /prompts/app/templates/{id}/sign      → Prompt App 签名
```

### 5.3 启用

```
POST /workspace/skills/{id}/enable         → Skill 启用（三道闸）
POST /workspace/agents/{id}/enable         → Agent 启用（三道闸）
POST /mcp/servers/{name}/enable            → MCP 启用（autosmoke + change-control）
POST /platform/workflows/{id}/toggle-enabled → Workflow 切换
```

### 5.4 发布

```
POST /platform/workflows/{id}/publish      → Workflow 发布
POST /platform/builder/projects/{id}/deploy-to-app → Builder 部署（验签门禁）
POST /prompts/app/templates/{id}/publish   → Prompt App 发布（验签门禁）
```

---

## 6 关键代码位置

### 6.1 密码学

| 文件 | 说明 |
|------|------|
| `aiPlat-core/core/harness/infrastructure/crypto/signature.py` | Ed25519 签名/验签/密钥生成 |
| `aiPlat-core/core/security/skill_signature_gate.py` | 签名门禁评估 + 审批创建 |
| `aiPlat-platform/api/routers/onboarding.py` | 密钥对生成 API + 可信公钥配置 |

### 6.2 门禁与权限

| 文件 | 说明 |
|------|------|
| `aiPlat-core/core/harness/infrastructure/gates/policy_gate.py` | PolicyGate: check_skill/check_tool/check_agent/check_workflow |
| `aiPlat-core/core/apps/tools/permission.py` | PermissionManager/RBAC |
| `aiPlat-core/core/governance/gating.py` | autosmoke_enforce/gate_with_change_control |
| `aiPlat-core/core/governance/changeset.py` | record_changeset 变更审计 |
| `aiPlat-core/core/governance/audit.py` | audit_event 审计事件 |

### 6.3 Entity Managers（溯源码 + 签名验签）

| 文件 | 实体 |
|------|------|
| `aiPlat-core/core/management/skill_manager.py` | Skills |
| `aiPlat-core/core/management/agent_manager.py` | Agents |
| `aiPlat-core/core/management/mcp_manager.py` | MCP |
| `aiPlat-core/core/apps/tools/discovery.py` | Tools |
| `aiPlat-core/core/management/workflow_manager.py` | Workflows |
| `aiPlat-platform/builder/builder_project_service.py` | Builder Projects |
| `aiPlat-core/core/management/prompt_app_manager.py` | Prompt Apps |

### 6.4 API 路由

| 文件 | 端点 |
|------|------|
| `aiPlat-core/core/api/routers/workspace_skills.py` | Skills CRUD + sign + enable |
| `aiPlat-core/core/api/routers/workspace_agents.py` | Agents CRUD + sign + enable |
| `aiPlat-core/core/api/routers/mcp_admin.py` | MCP CRUD + sign + enable |
| `aiPlat-core/core/api/routers/tools.py` | Tools CRUD + sign + execute |
| `aiPlat-platform/api/routers/workflows.py` | Workflows CRUD + sign + publish |
| `aiPlat-platform/api/routers/builder.py` | Builder CRUD + sign + deploy |
| `aiPlat-core/core/api/routers/prompt_app.py` | Prompt App CRUD + sign + publish |

### 6.5 前端

| 文件 | 签名 UI |
|------|---------|
| `Workspace/Skills/Skills.tsx` | 详情弹窗粘贴密钥签名 |
| `components/workspace/AgentDetailModal.tsx` | 详情弹窗粘贴密钥签名 |
| `Workspace/MCP/MCP.tsx` | 详情弹窗粘贴密钥签名 |
| `components/core/ToolDetailModal.tsx` | 详情弹窗粘贴密钥签名 |
| `Core/Workflows/WorkflowsPage.tsx` | 详情弹窗（Info 图标）签名 |
| `Prompts/AppTemplates.tsx` | 操作栏 Key 按钮 → 签名弹窗 |

### 6.6 Lint & 维护

| 文件 | 说明 |
|------|------|
| `aiPlat-core/core/management/skill_linter.py` | Lint 门面（20 条规则） |
| `aiPlat-core/core/management/lint_rules.yaml` | 声明式规则定义 |
| `aiPlat-core/core/management/lint_rules/governance.py` | 3 条治理规则 |
| `aiPlat-core/core/harness/maintenance/skill_lint_scan.py` | 定时批量巡检 |
| `aiPlat-core/core/apps/skills/curator.py` | 自动策展（stale/archived） |

### 6.7 设计文档

| 文件 | 说明 |
|------|------|
| `docs/governance.md` | **本文档** |
| `aiPlat-core/docs/contracts/05-governance-release-contract.md` | 治理/发布契约 |
| `aiPlat-core/docs/contracts/01-architecture-contract.md` | 架构契约 |

---

## 7 环境变量速查

| 变量 | 作用 | 默认值 |
|------|------|--------|
| `AIPLAT_APPROVALS_DISABLED` | 全局关闭审批 | `false` |
| `AIPLAT_SYSCALL_ENFORCE_APPROVAL` | syscall 层强制审批 | `false` |
| `AIPLAT_SKILL_PERMISSION_RULES` | Skill 权限规则 JSON | `{}` |
| `AIPLAT_EXEC_SKILL_PERMISSION_RULES` | 可执行 Skill 权限规则 JSON | `{}` |
| `AIPLAT_APPROVAL_REVIEW_MODE` | 审批模式 | `always` |
| `AIPLAT_APPROVAL_SAMPLE_RATE` | 采样审批率 | `0.0` |
| `AIPLAT_APPROVAL_LAYER_POLICY` | 审批层级策略 | `both` |
| `AIPLAT_STRICT_CODING_PROFILES` | 契约门禁强制 | `false` |
| `AIPLAT_HOME` | 数据根目录（entities/manifests） | `~/.aiplat` |
| `AIPLAT_TOOLS_PATH` | 用户工具目录 | `~/.aiplat/tools` |
| `AIPLAT_ENGINE_WORKFLOWS_PATH` | 引擎 workflow 目录 | `core/engine/workflows` |
| `AIPLAT_WORKSPACE_WORKFLOWS_PATH` | 工作区 workflow 目录 | `~/.aiplat/workflows` |

---

## 8 快速开始

### 8.1 生成签名密钥

```bash
# 通过 API 生成密钥对（私钥一次性展示，请妥善保存）
curl -X POST /api/core/onboarding/generate-skill-key -H "Authorization: Bearer $TOKEN"
# 返回: { "key_id": "...", "public_key": "-----BEGIN PUBLIC KEY-----...", "private_key": "-----BEGIN PRIVATE KEY-----..." }
```

### 8.2 对 Skill 签名

```bash
# 在管理端 UI 中操作：
# Workspace → Skills → 点击 Skill → 详情弹窗 → 粘贴私钥 → 点击"签名"
# 或通过 API：
curl -X POST /api/core/workspace/skills/{id}/sign \
  -H "Content-Type: application/json" \
  -d '{"private_key": "-----BEGIN PRIVATE KEY-----..."}'
```

### 8.3 启用 Skill

```bash
# 签名后，启用 Skill（自动验签 + 审批）
curl -X POST /api/core/workspace/skills/{id}/enable -H "Authorization: Bearer $TOKEN"
```

### 8.4 配置权限规则

```bash
export AIPLAT_SKILL_PERMISSION_RULES='{"*":"allow","secret-*":"deny","experimental-*":"ask"}'
```

### 8.5 查看审计记录

管理端 → 诊断中心 → ChangeControl / Audit — 所有变更和审计事件可查询。
