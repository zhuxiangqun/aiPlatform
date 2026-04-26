---
name: demo_double_approval_file_write
display_name: 双层审批写文件（示范）
description: 同时触发 skill 审批与 tool(file_operations) 审批，用于验证“分层审批策略”配置是否生效（skill_only / tool_only / both）。
category: execution
version: 0.1.0
skill_kind: executable
permissions:
  - tool:file_write
auto_trigger_allowed: false
requires_approval: true
trigger_conditions:
  - 双层审批
  - 写文件审批策略
input_schema:
  type: object
  properties:
    path:
      type: string
      description: 绝对路径（必须在 AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS 之内）
    content:
      type: string
      description: 写入内容
  required: [path, content]
output_schema:
  type: object
  properties:
    path: {type: string}
    bytes_written: {type: integer}
    sha256: {type: string}
---

# 双层审批写文件（示范）

该技能会：
1) 触发 skill 层审批（requires_approval=true）
2) 在执行时调用 file_operations 写入，并强制 `_approval_required=true`（触发 tool 层审批）

用于验证分层审批策略：
- both：会出现双层审批（skill + tool）
- skill_only：只审批 skill，tool 自动复用 skill 的 approval_request_id，不再二次审批
- tool_only：跳过 skill 审批，只在 tool 层审批

