---
name: chitchat
display_name: 闲聊
description: 处理日常闲聊和简单问答。触发条件：问候、闲聊、简单常识。跳过条件：涉及代码、数据、专业任务。涉及数据库相关操作。 主要进行审查。
category: generation
version: 1.0.0
status: enabled
protected: true
execution_mode: prompt
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