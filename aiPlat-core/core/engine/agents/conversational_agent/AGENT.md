---
name: conversational_agent
display_name: 对话代理
description: 基于对话模式的通用 Agent。引擎内置（engine）：仅核心能力层默认可用。
agent_type: conversational
version: 1.0.0
status: running
protected: true
category: engineering
tags:
- conversational
- chat
skills:
- chitchat
- translation
- text_generation
- code-hygiene
- grilling
tools:
- sysgraph_search
- sysgraph_context
model: deepseek-chat
config:
  system_prompt: 你是 conversational_agent，基于对话模式的通用 Agent。引擎内置（engine）：仅核心能力层默认可用。
  model: deepseek-chat
---


## 交接协议 (Handoff)

**做了什么**: 执行 conversational_agent 的 SOP 定义的任务
**产出物在哪**: state[output_artifact] 中
**如何验证**: 检查 output_artifact 是否存在且非空
**已知问题**: Engine seed — 完整 SOP 需在 workspace agent 中定义
**下一步**: 下游阶段读取本阶段的产出物继续执行

> 探索代码结构时优先用 sysgraph_* 工具（比 grep/read 快 10×）
