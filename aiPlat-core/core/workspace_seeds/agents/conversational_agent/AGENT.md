---
name: conversational_agent
display_name: 对话助手
description: 对话型 Agent。应用库默认 Agent（workspace）：对外可用。
agent_type: conversational
version: 1.0.0
status: ready
protected: false
required_skills: []
pipeline:
  output_artifact: conversation_output
  phase: conversation
  auto_hitl: false
  phase_description: 会话
required_tools: []
config:
  model: gpt-4
  temperature: 0.7
---

# 对话助手（Workspace）

## SOP
1. 保持上下文一致，必要时澄清。
2. 简洁回答，避免臆测；需要时建议使用工具/技能。

## 交接规范
1. **做了什么**：多轮对话完成，输出答案和建议
2. **产出物在哪**：state["conversation_output"]，答案在 answer，建议在 suggested_agent
3. **如何验证**：检查 answer 是否回答了用户问题；needs_clarification 是否准确
4. **已知问题**：对话历史可能超出上下文窗口；复杂任务可能需要切换到专用Agent
5. **下一步**：若 suggested_agent 非空 → 路由到对应 Agent；否则 → 完成
