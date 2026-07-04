# governance 模块（Platform Layer 2：治理与合规）

## 定位

`governance/` 提供限流、熔断、审计、配额管理等平台级治理能力。所有 API 请求在进入业务逻辑前先经治理层检查。

## 已实现能力

| 能力 | 代码位置 | 状态 |
|------|---------|:--:|
| Rate Limiter（滑动窗口限流） | platform/governance/rate_limit/ | ✅ |
| Circuit Breaker（熔断器） | platform/governance/ | ✅ |
| Quota Manager（配额管理） | platform/governance/quota/ | ✅ |
| Audit Logger（审计日志链式哈希） | platform/governance/audit/logger.py | ✅ |
| SHA-256 防篡改 | governance/audit/logger.py → verify_integrity() | ✅ |
| Compliance Checks（SOC2/ISO27001 映射） | core/management/compliance_checks.py | ✅ |

## 边界

- 治理层做"限速"和"记录"，不做权限判断（权限在 PolicyGate）
- 审计日志写入 SQLite（`~/.aiplat/`），不依赖外部日志系统
- 熔断和限流策略通过环境变量配置（`AIPLAT_CIRCUIT_COOLDOWN` 等）
