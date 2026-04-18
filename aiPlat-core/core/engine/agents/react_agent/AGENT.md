---
name: react_agent
display_name: ReAct助手
description: 通用 ReAct Agent。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
agent_type: react
version: 1.0.0
status: ready
protected: true
required_tools: []
required_skills: []
config:
  model: gpt-4
---

# ReAct助手（Engine）

## SOP
1. 理解任务与约束，必要时澄清。
2. 推理-行动-观察循环使用工具/技能。
3. 输出结论与关键依据。
