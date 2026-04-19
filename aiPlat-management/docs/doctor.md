# Doctor（一键自检）

Doctor 用于将常见“上线可用性检查”收敛为一个接口与一个页面，减少运维排障成本。

## API

`GET /api/diagnostics/doctor`

聚合内容（MVP）：
- infra/core/platform/app 健康状态（同 `/diagnostics/health/all`）
- core adapters 概览（是否已配置模型）
- autosmoke 相关 env 提示（best-effort）
- 强门禁（default tenant）状态提示：是否启用了 `approval_required_tools=['*']`
- links/actions：UI/API 的跳转与一键操作入口
- recommendations：按严重级别给出可执行建议

管理台 Doctor 页面会对报告中的 `actions` / `recommendations[*].actions` 做“可执行按钮”渲染：
- 执行以 `action_type` 为主（白名单），避免任意 API 调用
- 为兼容旧版本，也支持按 `api_url`（同样白名单）
- 若 action 提供 `input_schema`（JSON schema），UI 会自动渲染最小参数表单；否则回退展示 `body_example`。
- input_schema 支持基础字段说明与 UI 提示：
  - `description`：字段解释
  - `x-ui.placeholder`：输入提示
  - `x-ui.sensitive`：敏感字段（UI 脱敏显示为 "***"）
  - `x-ui.hidden`：隐藏字段（UI 不显示，但可使用默认值）
  - `x-ui.order`：字段排序（数值越小越靠前）
  - `x-ui.multiline`：多行输入（textarea）

## UI

管理台 → 可观测性 → Doctor  
路由：`/diagnostics/doctor`

页面提供的一键动作：
- **一键跑 Smoke**：触发 `POST /api/diagnostics/e2e/smoke`
- **复制报告**：复制 doctor JSON
- **下载 JSON**：下载本次 doctor 报告
- **去初始化向导**：跳转 `/onboarding`

## 常见建议解读

- `autosmoke_disabled`：建议开启 `AIPLAT_AUTOSMOKE_ENABLED=true`
- `autosmoke_gate_off`：如需强门禁开启 `AIPLAT_AUTOSMOKE_ENFORCE=true`
- `autosmoke_no_alerts`：如需失败告警设置 `AIPLAT_AUTOSMOKE_WEBHOOK_URL`
- `unhealthy_layers`：存在不健康层，建议先修复 health 再跑 smoke
- `no_adapters`：尚未配置任何 LLM adapter，先去“初始化向导”配置模型
