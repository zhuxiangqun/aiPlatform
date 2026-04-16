# Round8 复审变更日志（持续交付｜历史记录）

> **历史报告**：本日志服务于 `reports/audit_findings_round8.json` 与对应 docx 复审报告，用于回溯 Round8 的实现修复与验证命令；当前实现以最新代码与测试为准。

## 变更记录

### 2026-04-16
- 实施修复：
  - CORE-ROUTING-001：消除 Skill/Tool substring 误触发：新增 parse_action_call（显式 skill 调用），ReActLoop 移除 substring skill fallback，PlanExecuteLoop 移除 substring tool/skill dispatch；补齐回归测试与 ARCHITECTURE_STATUS 证据链。

