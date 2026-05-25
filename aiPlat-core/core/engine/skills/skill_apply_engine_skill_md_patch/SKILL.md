---
name: skill_apply_engine_skill_md_patch
display_name: 应用 Engine Skill 补丁
description: 应用 engine skill 的 SKILL.md 补丁（change-control 治理）。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: ops
version: 1.0.0
status: enabled
protected: true
execution_mode: prompt
permissions:
  - "fs:write"
effects:
  - type: write
    resources: ["filesystem:~/.aiplat"]
    idempotent: true
    rollback_available: false
input_schema:
  skill_id:
    type: string
    required: true
  patch:
    type: string
    required: true
output_schema:
  result:
    type: object
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 应用 Engine Skill 补丁（Engine）

## SOP
1. 校验补丁格式和签名。
2. 对目标 SKILL.md 做安全审计后应用补丁。
3. 输出变更摘要：修改行数、新增字段、风险评估。
