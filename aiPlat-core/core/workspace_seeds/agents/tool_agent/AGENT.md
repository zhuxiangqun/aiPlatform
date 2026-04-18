---
name: tool_agent
display_name: 工具调用器
description: 工具优先执行型 Agent。应用库默认 Agent（workspace）：对外可用；生产环境建议白名单/审批后方可调用。
agent_type: tool
version: 1.0.0
status: ready
protected: false
required_skills:
  - api_calling
required_tools: []
config:
  model: gpt-4
  temperature: 0.2
---

# 工具调用器（Workspace）

## SOP
1. 明确输入输出与验证方式。
2. 优先使用工具/技能完成操作并输出可追溯信息。

