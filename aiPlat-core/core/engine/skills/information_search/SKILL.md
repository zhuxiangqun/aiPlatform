---
name: information_search
display_name: 信息检索
description: 从知识库和互联网中检索相关信息。触发条件：用户要求搜索、检索、查找资料。跳过条件：内部知识库查询由 knowledge_retrieval
  处理。 涉及信息相关操作。 主要进行搜索。
category: retrieval
version: 1.0.0
status: enabled
protected: true
completion_criterion: |
  1. 用户的问题已被直接完整回答
  2. 回答长度与问题复杂度匹配（不冗长不敷衍）
  3. 如需后续操作，已明确告知用户下一步做什么
execution_mode: prompt
permissions:
- web:search
- kb:query
effects:
- type: read
  resources:
  - filesystem:~/.aiplat
  idempotent: true
  rollback_available: false
input_schema:
  query:
    type: string
    required: true
  sources:
    type: array
    description: 检索源，如 kb, web
output_schema:
  results:
    type: array
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
metadata:
  trigger_conditions:
  - 搜索
  - 检索
  - 查找信息
  - 信息检索
  - 查资料
  - 搜索资料
  - 检索信息
  - 查找文档
  keywords:
    objects:
    - 信息
    - 资料
    - 文档
    - 数据源
    actions:
    - 搜索
    - 检索
    - 查询
    - 查找
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 从多数据源检索并融合信息
keywords:
  objects:
  - 资料
  - 信息
  - 文档
  - 论文
  - 新闻
  actions:
  - 搜索
  - 查找
  - 检索
  - 调研
  constraints:
  - 时效性
  - 来源可靠性
trigger_conditions:
- when: 用户要求搜索信息
  query: 搜索/查找/调研
- when: 不应用场景
  description: 跳过条件：用户已明确知道答案或仅需确认时不触发。
skip_when: 跳过条件：用户已明确知道答案或仅需确认时不触发。
---



# 信息检索（Engine）

## SOP
1. 分析查询意图，确定检索源和范围。
2. 执行多源检索并对结果去重排序。
3. 输出相关性排序的结果列表及每条的去源信息。

## 目标
从多数据源检索并融合信息

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注