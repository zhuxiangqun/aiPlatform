---
name: task_planning
display_name: 任务规划
description: 将目标拆解为可执行计划。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: execution
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
input_schema:
  goal:
    type: string
    required: true
output_schema:
  plan:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 任务规划（Engine）

## SOP
1. 明确目标/范围/验收标准/截止时间。
2. 分阶段拆解步骤并标注依赖与风险。
3. 每阶段给出验证方式与回滚建议。
