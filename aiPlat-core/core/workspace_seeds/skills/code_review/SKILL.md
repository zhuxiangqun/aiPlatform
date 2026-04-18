---
name: code_review
display_name: 代码审查
description: 审查代码质量并给出改进建议。应用库默认技能（workspace）：对外可用；注意代码/日志脱敏与权限隔离。
category: analysis
version: 1.0.0
status: enabled
protected: false
execution_mode: inline
input_schema:
  diff_or_code:
    type: string
    required: true
output_schema:
  review:
    type: string
---

# 代码审查（Workspace）

## SOP
1. 概览：代码做什么、关键假设。
2. 正确性/可维护性/安全性/性能逐项检查。
3. 输出 Blocking 与 Non-blocking，并给出可落地修改建议。

