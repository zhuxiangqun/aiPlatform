---
name: chitchat
display_name: 闲聊
description: 处理日常闲聊和简单问答。触发条件：用户消息为问候、闲聊、简单常识问题、非技术对话。跳过条件：涉及代码、数据、搜索等专业任务时由对应 Skill 处理。
category: generation
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
