---
name: summarization
display_name: 内容摘要
description: 将长文本压缩为结构化摘要。触发条件：用户要求总结、摘要、概括、提炼要点。跳过条件：需要原始数据时不适用。 涉及文本相关操作。 主要进行摘要。
category: transformation
version: 1.0.0
status: enabled
protected: true
completion_criterion: |
  1. 输出符合 ## FILE: 格式规范
  2. 每个文件包含完整可运行代码
  3. 所有依赖项已声明，所有外部引用已校验
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
  text:
    type: string
    required: true
output_schema:
  summary:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
metadata:
  trigger_conditions:
  - 摘要
  - 总结
  - 概括
  - 要点提炼
  - 内容摘要
  - 摘要生成
  - 概括内容
  - 提炼要点
  keywords:
    objects:
    - 文本
    - 文档
    - 内容
    actions:
    - 摘要
    - 总结
    - 概括
    - 压缩
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 将长文本压缩为结构化摘要
keywords:
  objects:
  - 文章
  - 文档
  - 报告
  - 对话
  - 长文本
  actions:
  - 总结
  - 归纳
  - 概括
  - 摘要
  constraints:
  - 不超过500字
  - 保留关键信息
trigger_conditions:
- when: 用户要求总结或归纳内容
  query: 总结/归纳/概括
- when: 不应用场景
  description: 跳过条件：仅需要列出事实而不需要归纳时不触发。
skip_when: 跳过条件：仅需要列出事实而不需要归纳时不触发。
---



# 内容摘要（Engine）

## SOP
1. 提取主题、结论、关键数据与行动项。
2. 输出：TL;DR + 要点列表 + 待确认问题。
3. 长文按章节总结并标注标题。

## 目标
将长文本压缩为结构化摘要

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注