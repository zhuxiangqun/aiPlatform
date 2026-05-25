---
name: task_planning
display_name: 任务规划
description: 将目标拆解为可执行计划。触发条件：用户描述"怎么实现""拆一下""分几步"等需求。跳过条件：单步骤任务直接执行。
category: execution
version: 1.0.0
status: enabled
protected: true
execution_mode: prompt
permissions:
  - "llm:generate"
effects:
  - type: read
    resources: ["filesystem:~/.aiplat"]
    idempotent: true
    rollback_available: false
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
