---
name: task_decomposition
display_name: 任务分解
description: 将复杂任务分解为子任务与依赖（引擎内置）。
category: analysis
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
input_schema:
  task:
    type: string
    required: true
output_schema:
  subtasks:
    type: string
---

# 任务分解（Engine）

## SOP
1. 明确交付物与验收标准。
2. 分解为子任务，标注输入/输出/依赖/优先级/风险。
3. 给出推荐执行顺序与里程碑。
