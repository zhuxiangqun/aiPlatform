# Private Control Plane — 内部治理平面

> **本文档为 PolicyGate/ApprovalGate 的权威参考入口。** 相关内容参见：`governance.md`、`eu-ai-act-compliance.md`、`private-control-plane.md`

> 本文档为架构治理中 PolicyGate / ApprovalGate / 审计日志等组件的权威参考入口。

## 核心组件

| 组件 | 位置 | 说明 |
|------|------|------|
| PolicyGate | `core/harness/infrastructure/gates/policy_gate.py` | 工具/技能调用前的策略校验 |
| ApprovalGate | `core/harness/infrastructure/gates/approval_gate.py` | 高风险操作审批门 |
| 审计日志 | `core/harness/observability/audit.py` | 全链路可追溯 |

> 详细实现参见 `governance.md` 和 `eu-ai-act-compliance.md`。
