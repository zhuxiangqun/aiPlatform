---
name: code_review
display_name: 代码审查
description: 审查代码质量并给出改进建议。应用库默认技能（workspace）：对外可用；注意代码/日志脱敏与权限隔离。
category: analysis
version: 1.0.0
status: enabled
protected: false
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
input_schema:
  diff_or_code:
    type: string
    required: true
output_schema:
  report:
    type: object
    required: true
    description: 结构化审查结果（机器可读）
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 代码审查（Workspace）

## SOP
1. 概览：代码做什么、关键假设。
2. 正确性/可维护性/安全性/性能逐项检查。
3. 输出 Blocking 与 Non-blocking，并给出可落地修改建议。

## 输出格式（JSON + Markdown）
执行时请输出严格 JSON，包含两个字段：
- `report`：结构化对象（summary/blocking/non_blocking/risk 等，允许扩展）
- `markdown`：把上述内容渲染为 Markdown
