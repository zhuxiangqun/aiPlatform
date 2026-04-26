---
name: chitchat
display_name: 闲聊
description: 日常闲聊与简单问答。应用库默认技能（workspace）：对外可用。
category: generation
version: 1.0.0
status: enabled
protected: false
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

# 闲聊（Workspace）

## SOP
1. 识别意图：闲聊/情绪支持/简单问答/任务请求。
2. 友好简洁回应。
3. 如是任务请求，提出少量澄清并引导到任务模式。
