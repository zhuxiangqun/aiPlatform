---
name: grilling
display_name: 需求澄清追问
description: 当用户需求模糊时，逐一追问直到细节清晰。每次只问一个问题，附带推荐选项。如果可通过读已有文件/代码回答，读文件，别问用户。
category: analysis
version: 1.0.0
status: enabled
execution_type: prompt
sop_goal: "从用户描述中找出最模糊的点，逐一追问直到细节清晰"
sop_flow:
  - 从用户描述中找最模糊的点
  - 问一个问题附带推荐选项
  - 用户可A/B/C快速回答
  - 可读文件时读文件不追问
  - 重复直到需求完整
  - 输出结构化澄清摘要
input_schema:
  type: object
  properties:
    question:
      type: string
      description: 用户的原始需求描述或模糊问题
  required: [question]
output_schema:
  type: object
  properties:
    clarification_result:
      type: string
      description: 所有澄清问题的结构化摘要
    questions_asked:
      type: integer
      description: 追问了多少轮才达到明确
  required: [clarification_result]
  markdown:
    type: string
    required: true
completion_criterion: |
  1. 用户明确说"可以开始了"或"确认"或"没问题"
  2. 或连续两轮追问无新的实质性模糊点
  3. 输出一份包含所有澄清结果的结构化摘要
permissions:
  - llm:generate
effects:
  - type: read
    resources: [filesystem:~]
    idempotent: true
    rollback_available: false
negative_triggers:
  - 这不是模糊需求
  - 已经非常明确的任务
keywords:
  - 追问
  - 需求澄清
  - 结构化提问
  - 模糊需求
triggers:
  - 帮我做一个
  - 帮我优化一下
  - 帮我实现
  - 帮我写一个
  - 我想做一个
  - 能不能帮我
  - 帮我设计
  - trigger_conditions:
    - when: 用户需求缺少具体输入/输出/约束/指标/范围/边界
      query: 追问需求细节
---

## SOP

1. 从用户描述中找出最模糊的一个点——只选一个，不列清单
2. 问一个问题，附带 ≤3 个推荐选项，每个选项 ≤20 字说明
3. 用户可以直接说"A""B""C"而不需要打字
4. 如果可以通过读已有文件或代码回答当前问题 → 读文件，别问用户
5. 重复步骤 1-4，直到满足 completion_criterion
6. 输出一份 Markdown 结构化摘要：{需求概述, 关键决策, 输入/输出约定, 约束边界, 下一步建议}

## 示例

用户："帮我做一个后台管理系统"
→ "你提到后台管理系统——最需要先确认的是第一个模块做什么？A)用户管理 B)内容管理 C)数据看板"

用户："帮我优化一下这个接口"
→ "优化是指什么方向？A)响应速度 B)代码可读性 C)错误处理 D)安全性"
