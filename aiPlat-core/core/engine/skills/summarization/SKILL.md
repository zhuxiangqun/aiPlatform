---
name: summarization
display_name: 内容摘要
description: 将长文本压缩为结构化摘要。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: transformation
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
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
