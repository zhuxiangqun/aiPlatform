# Doctor（一键自检）

Doctor 用于将常见“上线可用性检查”收敛为一个接口与一个页面，减少运维排障成本。

## API

`GET /api/diagnostics/doctor`

聚合内容（MVP）：
- infra/core/platform/app 健康状态（同 `/diagnostics/health/all`）
- core adapters 概览（是否已配置模型）
- autosmoke 相关 env 提示（best-effort）
- recommendations：按严重级别给出可执行建议

## UI

管理台 → 可观测性 → Doctor  
路由：`/diagnostics/doctor`

## 常见建议解读

- `autosmoke_disabled`：建议开启 `AIPLAT_AUTOSMOKE_ENABLED=true`
- `autosmoke_gate_off`：如需强门禁开启 `AIPLAT_AUTOSMOKE_ENFORCE=true`
- `autosmoke_no_alerts`：如需失败告警设置 `AIPLAT_AUTOSMOKE_WEBHOOK_URL`
- `unhealthy_layers`：存在不健康层，建议先修复 health 再跑 smoke
- `no_adapters`：尚未配置任何 LLM adapter，先去“初始化向导”配置模型

