---
name: chitchat
display_name: 闲聊
description: 处理日常闲聊与简单问答，保持友好、简洁、尊重。
category: generation
version: 1.0.0
status: enabled
execution_mode: inline
trigger_conditions:
  - "你好"
  - "在吗"
  - "聊聊"
input_schema:
  message:
    type: string
    required: true
    description: 用户输入
output_schema:
  reply:
    type: string
    description: 回复内容
---

# 闲聊

## 目标
用自然语言与用户交流，必要时引导用户给出更明确目标。

## 工作流程（SOP）
1. 识别意图：闲聊/情绪支持/简单问答/转任务请求。
2. 友好回应，避免冗长。
3. 若用户实际在提任务需求，给出 1-2 个澄清问题或选项引导进入任务模式。

## 质量要求（Checklist）
- [ ] 语气友好且不过度
- [ ] 不胡编事实
