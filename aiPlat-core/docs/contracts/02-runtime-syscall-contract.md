# Runtime & Syscall Contract（运行时与系统调用契约）

本文件约束“执行边界”：什么必须在 syscall 内做、什么必须可观测、什么必须可恢复。

## 1. ActiveRequestContext（MUST）

每次执行（agent/tool/skill/job/gateway）都 **MUST** 具备可追踪上下文，至少包含：
- `tenant_id`（若有多租户）
- `actor_id/user_id`
- `session_id`
- `entrypoint`（api/gateway/subagent/cron/job…）
- `trace_id`、`run_id`（若可用）

上下文传播 **MUST**：
- 在 syscall 边界（llm/tool/skill/exec）记录到 run_events / syscall_events（若启用）
- 不得通过全局变量泄漏到其他请求（使用 contextvars 或等效机制）

## 2. Syscall 边界（MUST）

系统调用由 Harness/Kernel 发起，典型包括：
- `sys_llm_generate`
- `sys_tool_call`
- `sys_skill_call`

约束：
- syscall **MUST NOT** 因“可选能力失败”导致主循环崩溃（best-effort + 降级）
- syscall **MUST** 产生可观测事件（至少：开始/结束、耗时、错误码、关键统计）
- syscall 返回 **MUST** 使用结构化结果（ok/错误/耗时/metadata）

## 3. LLM 消息输入保护（MUST）

在 `sys_llm_generate` 边界处 **MUST**：
- 修复不合法 role（例如 tool role），避免供应商拒收
- 合并相邻同 role 消息（减少 token 噪声）
- 对单条消息与整体输入做字符/体积限制（通过 env 配置），并记录 guard 统计到事件

## 4. 恢复/重试语义（SHOULD）

当出现需要人工批准或策略拒绝：
- 系统 **SHOULD** 给出可执行的下一步指导（例如“改用 tool_search”或“缩小权限范围”）
- 系统 **MAY** 在可控阈值内自动重试（必须有上限，避免死循环）

## 5. 错误码与错误信封（MUST）

所有可预期错误 **MUST** 有稳定错误码（示例）：
- `policy_denied`
- `approval_required`
- `tool_not_found`
- `invalid_tool_args`
- `llm_provider_error`
- `timeout`

错误信息 **MUST**：
- 对用户可理解
- 不泄漏密钥/内部路径/敏感上下文（必要时截断/脱敏）

