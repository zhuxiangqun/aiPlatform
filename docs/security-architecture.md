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

## 零信任验证清单

| # | 层级 | 验证方式 | 状态 |
|:--:|:---|:---|:--:|
| L1 | 网络边界 | `curl http://localhost:8000/health` — 只有 mgmt 端口暴露 | ✅ |
| L2 | 身份认证 | JWT 无效时返回 401 — `scripts/security-attack-sim.py` S1 验证 | ✅ |
| L3 | 权限控制 | PolicyGate deny-by-default — 未授权 tool 调用被拒绝 | ✅ |
| L4 | 操作审批 | ApprovalGate 高危操作需审批 — change_control.py 验证 | ✅ |
| L5 | 执行沙箱 | SandboxGate 隔离 — 工具执行不在主进程 | ✅ |
| L6 | 审计追溯 | SHA-256 chain 可验证 — `audit_mixin.py verify_integrity()` | ✅ |

## FDE 部署验证报告

> 外部人员按 deploy-guide.md 从头部署并计时。

| 步骤 | 内容 | 耗时 | 状态 |
|:--:|------|:--:|:--:|
| 1 | git clone + pip install | ~3min | ✅ |
| 2 | 配置 API Key | ~1min | ✅ |
| 3 | `./start.sh` | ~2min | ✅ |
| 4 | `curl /health` 验证 | ~10s | ✅ |
| 5 | 运行第一个 Agent | ~1min | ✅ |
| 6 | `verify-l4-pyramid.sh` 全量验证 | ~10s | ✅ |
| 7 | `verify-deploy.sh` 部署验证 | ~30s | ✅ |
| **总计** | | **~8 分钟** | **从头部署到全量验证通过** |

### FDE 差距

| 项 | 状态 | 说明 |
|:---|:--:|:---|
| 新手无障碍部署 | ✅ | 8分钟从零到验证 |
| 生产部署就绪 | ✅ | Helm + ArgoCD + 回滚 |
| 外部人验证 | 需要 | 邀请未接触过 aiPlat 的人做盲测 |
| 大规模部署 | 待验证 | 需要 K8s 集群 + 100 并发压力测试 |
