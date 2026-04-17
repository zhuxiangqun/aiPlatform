---
name: summarization
display_name: 内容摘要
description: 将长文本压缩为结构化摘要（要点、结论、行动项）。
category: transformation
version: 1.0.0
status: enabled
execution_mode: inline
trigger_conditions:
  - "总结一下"
  - "帮我摘要"
  - "提炼要点"
input_schema:
  text:
    type: string
    required: true
    description: 需要摘要的原文
output_schema:
  summary:
    type: string
    description: 摘要内容
---

# 内容摘要

## 目标
把原文压缩为可快速阅读的摘要，并保留关键信息不失真。

## 工作流程（SOP）
1. 识别主题、结论、关键数据、关键人物/系统/时间点。
2. 输出三层摘要（可按需选择）：
   - TL;DR（3-5 行）
   - 要点列表（5-12 条）
   - 行动项/风险/待确认问题
3. 原文较长时，按章节组织摘要并标注段落主题。

## 质量要求（Checklist）
- [ ] 不改变原意
- [ ] 保留关键数据与约束条件
- [ ] 摘要结构清晰
