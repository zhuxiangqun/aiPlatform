# Round2 复审变更日志（持续交付｜历史记录）

> **历史报告**：本日志服务于 `reports/audit_findings_round2.json` 与对应 docx 复审报告，用于回溯当时修复项与验证命令；当前实现以最新代码与测试为准。

> 说明：本日志服务于 `reports/audit_findings_round2.json` 与对应 docx 复审报告。

## 变更记录

### 2026-04-15
- 初始化：基于全量设计文档（core/infra/management）与代码实现进行 Round2 复审，输出新的审查项清单与改进建议。
- 设计补丁包：为核心设计文档补齐可操作规范（权限闭环、版本回滚语义、运行时治理 Hook 契约、观测驱动控制闭环、Agent 状态统一），并修正文档路径/存在性/依赖方向等偏差；同步更新 Round2 审查项状态与报告。
- 实施修复：
  - R2-AUTH-001：新增权限管理 API（grant/revoke/query/stats），并在 server 启动时默认 seed system/admin 对已注册 agent/skill/tool 的 EXECUTE 权限（支持环境变量关闭）。
  - R2-SKILL-VERSION-SEM-001：补齐 Skill 回滚语义（回滚影响实例 config + active_version 查询），并修复 rollback endpoint 校验与返回结构，新增单测覆盖。
  - R2-HOOK-SEC-001：治理 HookPhase 已接入执行主路径（SESSION/CONTRACT/STOP/APPROVAL），HookManager 默认注册最小安全钩子，并支持 hook 返回 allow=false 阻断执行；新增单测覆盖。
  - R2-OBS-CONTROL-001：实现最小“观测驱动控制”闭环：采集 tool_error_rate 并在阈值触发时将 Loop 置为 PAUSED（require_manual），同时支持 token 高占用的 best-effort context 压缩；新增单测覆盖。
  - R2-TOOL-THREADSAFE-001：为 BaseTool stats 与 ToolRegistry 操作加锁（线程安全最小集），并在 _call_with_tracking 中接入 tracer.start_span（可选）；新增多线程单测验证统计一致性。
  - R2-AGENT-STATE-001：Agent 状态模型收敛到 canonical（AgentStateEnum）：management 输出规范化状态值，execution registry 默认状态改为 ready，并新增单测覆盖。
