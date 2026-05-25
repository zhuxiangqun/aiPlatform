---
name: summarization
display_name: 内容摘要
description: 将长文本压缩为结构化摘要。触发条件：用户要求总结、摘要、概括、提炼要点。跳过条件：需要原始数据时不适用。
category: transformation
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
---

# 内容摘要（Engine）

## SOP
1. 提取主题、结论、关键数据与行动项。
2. 输出：TL;DR + 要点列表 + 待确认问题。
3. 长文按章节总结并标注标题。
