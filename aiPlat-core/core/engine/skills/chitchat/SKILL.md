---
name: chitchat
display_name: 闲聊
description: 处理日常闲聊和简单问答。触发条件：问候、闲聊、简单常识。跳过条件：涉及代码、数据、专业任务。涉及数据库相关操作。 主要进行审查。
category: generation
version: 1.0.0
triggers:
- 聊天
- 对话
- 问候
- 沟通
- 闲聊
status: enabled
protected: true
completion_criterion: |
  1. 用户的问题已被直接完整回答
  2. 回答长度与问题复杂度匹配（不冗长不敷衍）
  3. 如需后续操作，已明确告知用户下一步做什么
execution_mode: prompt
execution_type: prompt
permissions:
- llm:generate
effects:
- type: read
  resources:
  - filesystem:~/.aiplat
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
metadata:
  trigger_conditions:
  - 闲聊
  - 聊天
  - 随便聊聊
  - 你好
  - 介绍你自己
  - 讲个笑话
  - 天气怎么样
  - 早上好
  - 晚安
  - 谢谢
  keywords:
    objects:
    - 日常对话
    - 问候
    - 闲聊话题
    actions:
    - 聊天
    - 回复
    - 回答
    - 问候
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 提供友好自然的日常对话服务
sop_flow:
  - "闲聊（Engine）"
  - "理解用户意图：纯闲聊 vs 混杂信息需求。"
  - "友好自然地回复，必要时引导至其他 Skill。"
  - "不输出未经确认的事实信息。"
  - "提供友好自然的日常对话服务"
  - "[ ] 输出格式符合规范"
  - "[ ] 正确处理错误和边界条件"
  - "[ ] 返回结果包含引用和来源标注"
keywords:
  objects:
  - 闲聊话题
  - 日常对话
  - 问候
  actions:
  - 聊天
  - 对话
  - 回应
  constraints:
  - 友好
  - 简洁
  - 自然
trigger_conditions:
- when: 用户发起闲聊或问候
  query: 你好/天气/笑话
- when: 不应用场景
  description: 跳过条件：用户明确要求执行特定任务（非闲聊）时不触发。
skip_when: 跳过条件：用户明确要求执行特定任务（非闲聊）时不触发。
---



# 闲聊（Engine）

## SOP
1. 理解用户意图：纯闲聊 vs 混杂信息需求。
2. 友好自然地回复，必要时引导至其他 Skill。
3. 不输出未经确认的事实信息。

## 目标
提供友好自然的日常对话服务

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注