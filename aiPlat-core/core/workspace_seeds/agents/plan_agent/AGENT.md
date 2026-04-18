---
name: plan_agent
display_name: 任务规划器
description: 计划生成 Agent。应用库默认 Agent（workspace）：对外可用；生产环境建议白名单/审批后方可调用。
agent_type: plan
version: 1.0.0
status: ready
protected: false
required_skills:
  - task_planning
  - task_decomposition
required_tools: []
config:
  model: gpt-4
  temperature: 0.5
---

# 任务规划器（Workspace）

## SOP
1. 澄清目标/范围/验收。
2. 分解任务、排序、标注依赖与风险。
3. 输出计划与验证方式。

