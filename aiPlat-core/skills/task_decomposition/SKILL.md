---
name: task_decomposition
display_name: 任务分解
description: 将复杂任务分解为简单子任务，并给出依赖关系与优先级。
category: analysis
version: 1.0.0
status: enabled
execution_mode: inline
trigger_conditions:
  - "分解任务"
  - "拆成子任务"
  - "拆解一下"
input_schema:
  task:
    type: string
    required: true
    description: 需要分解的任务
output_schema:
  subtasks:
    type: string
    description: 子任务列表与依赖
---

# 任务分解

## 目标
把复杂任务拆成可并行、可验收、可分配的子任务。

## 工作流程（SOP）
1. 明确最终交付物与验收标准。
2. 按模块/阶段/风险点分解成子任务（建议 8-30 个）。
3. 标注每个子任务：
   - 输入/输出
   - 依赖（前置任务/外部依赖）
   - 风险等级与优先级
4. 给出建议的执行顺序与里程碑。

## 质量要求（Checklist）
- [ ] 子任务粒度合适（可在 0.5-2 天内完成为宜）
- [ ] 依赖关系明确
