---
name: summarization
display_name: 内容摘要
description: 将长文本压缩为结构化摘要（引擎内置）。
category: transformation
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
input_schema:
  text:
    type: string
    required: true
output_schema:
  summary:
    type: string
---

# 内容摘要（Engine）

## SOP
1. 提取主题、结论、关键数据与行动项。
2. 输出：TL;DR + 要点列表 + 待确认问题。
3. 长文按章节总结并标注标题。
