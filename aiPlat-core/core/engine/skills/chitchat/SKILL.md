---
name: chitchat
display_name: 闲聊
description: 处理日常闲聊和简单问答。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: generation
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
input_schema:
  message:
    type: string
    required: true
output_schema:
  reply:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 闲聊（Engine）

## SOP
1. 理解用户意图：纯闲聊 vs 混杂信息需求。
2. 友好自然地回复，必要时引导至其他 Skill。
3. 不输出未经确认的事实信息。
