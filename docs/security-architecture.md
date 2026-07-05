# aiPlat 安全架构 — 纵深防御模型

> 基于零信任原则 (never trust, always verify) 的六层防御体系。

## 防御层级

| 层 | 名称 | 机制 | 实现 |
|:--:|:---|:---|:---|
| **L1** | 网络边界 | API 网关, TLS, CORS | Management API Gateway (port 8000) |
| **L2** | 身份认证 | JWT Bearer Token | 单用户模式可选, 多租户强制 |
| **L3** | 权限控制 | RBAC + PBAC | PolicyGate (deny-by-default) + Permission Check |
| **L4** | 操作审批 | HITL Approval | ApprovalGate + 审批申请/批准/拒绝 |
| **L5** | 执行沙箱 | Isolated Subprocess | SandboxGate — 工具执行隔离 |
| **L6** | 审计追溯 | SHA-256 Chain | Audit Mixin — 回查每条操作 |

## 零信任原则落地

| 原则 | aiPlat 实现 |
|:---|:---|
| 持续验证 | PolicyGate 每次 syscall 前检查权限 |
| 最小权限 | deny-by-default 策略, 必须显式授权 |
| 微分段 | Skill/Tool/Agent 权限独立, 互不继承 |
| 假定被破 | SandboxGate 隔离, 工具执行不在主进程 |
| 全程审计 | SHA-256 hash chain, 每次操作不可否认 |

## 安全边界

```
Internet → Management Gateway (唯一入口)
              ↓ PolicyGate (RBAC 检查)
              ↓ API 路由
              ├── Core (Agent Engine + Pipeline)
              │     ↓ ApprovalGate (高危操作审批)
              │     ↓ SandboxGate (工具执行隔离)
              ├── Infra (Model Management + LLM)
              │     ↓ SecretsManager (AES-256-GCM 密钥)
              └── Platform (Knowledge Base + Builder)
                    ↓ Audit Log (SHA-256 chain)
```

## GitHub Branch Protection Rules (Recommended)

```yaml
# Apply in GitHub → Settings → Branches → Add rule
branches: [main]
rules:
  - require_pull_request: true
    required_approvals: 1
    dismiss_stale_reviews: true
  - require_status_checks: true
    contexts: ["Lint & Type Check", "Test (pytest)", "L5 Depth Tests"]
  - require_conversation_resolution: true
  - require_code_owner_review: false  # no CODEOWNERS file
  - enforce_admins: true
```
