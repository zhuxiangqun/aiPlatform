---
name: task_decomposition
display_name: 任务分解
description: 将复杂任务分解为子任务与依赖。触发条件：用户描述的任务过于复杂、多个步骤、有依赖关系。跳过条件：单步骤任务由 task_planning 处理。
category: analysis
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
  task:
    type: string
    required: true
output_schema:
  subtasks:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 任务分解（Engine）

## SOP
1. 明确交付物与验收标准。
2. 分解为子任务，标注输入/输出/依赖/优先级/风险。
3. 给出推荐执行顺序与里程碑。
