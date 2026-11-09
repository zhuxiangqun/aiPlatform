# W1-1 Staging fail-closed 故障注入证据卡

> **仅 staging**。禁止生产破坏性注入。

| 字段 | 值 |
|---|---|
| 日期 (UTC) | |
| 环境 | staging |
| 操作人 | |
| 注入方式 | PolicyGate store 故障 / `AIPLAT_POLICY_FAIL_MODE` 临时故障路径 |
| 敏感调用结果 | 拒绝 / 其它（须拒绝） |
| 审计事件 ID/路径 | |
| 恢复验证 | `security_ops_audit.py --profile-matrix` 输出粘贴路径 |
| 结论 | `pass` / `fail` |
