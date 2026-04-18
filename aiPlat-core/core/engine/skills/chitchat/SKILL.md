---
name: chitchat
display_name: 闲聊
description: 日常闲聊与简单问答。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: generation
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
input_schema:
  message:
    type: string
    required: true
output_schema:
  reply:
    type: string
---

# 闲聊（Engine）

## SOP
1. 识别意图：闲聊/情绪支持/简单问答/任务请求。
2. 友好简洁回应。
3. 如是任务请求，提出少量澄清并引导到任务模式。
