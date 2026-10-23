# Private Control Plane — 内部治理平面

> **C2 消歧 / SoT**：本文是架构簇内 **PolicyGate / ApprovalGate 权威入口（短索引）**。  
> 对外长文/四层防御叙述见 [`docs/articles/private-control-plane.md`](../articles/private-control-plane.md)——**同名异职：短入口 vs 文章，勿合并正文**。

> 相关约束正文：[`governance.md`](./governance.md)、[`eu-ai-act-compliance.md`](./eu-ai-act-compliance.md)。

## 核心组件

| 组件 | 位置 | 说明 |
|------|------|------|
| PolicyGate | `core/harness/infrastructure/gates/policy_gate.py` | 工具/技能调用前的策略校验 |
| ApprovalGate | `core/harness/infrastructure/gates/approval_gate.py` | 高风险操作审批门 |
| 审计日志 | `core/harness/observability/audit.py` | 全链路可追溯 |

> 实现细节与四层防御叙事：[`../articles/private-control-plane.md`](../articles/private-control-plane.md)。  
> 治理与合规条文：[`governance.md`](./governance.md)、[`eu-ai-act-compliance.md`](./eu-ai-act-compliance.md)。
