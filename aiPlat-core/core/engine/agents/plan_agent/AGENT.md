---
name: plan_agent
display_name: 任务规划器
description: 计划生成 Agent（引擎内置）。
agent_type: plan
version: 1.0.0
status: ready
protected: true
required_skills:
  - task_planning
  - task_decomposition
required_tools: []
config:
  model: gpt-4
  temperature: 0.5
---

# 任务规划器（Engine）

## SOP
1. 澄清目标/范围/验收。
2. 分解任务、排序、标注依赖与风险。
3. 输出计划与验证方式。
