---
name: code_review
display_name: 代码审查
description: 审查代码质量并给出改进建议（引擎内置）。
category: analysis
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
input_schema:
  diff_or_code:
    type: string
    required: true
output_schema:
  review:
    type: string
---

# 代码审查（Engine）

## SOP
1. 概览：代码做什么、关键假设。
2. 正确性/可维护性/安全性/性能逐项检查。
3. 输出 Blocking 与 Non-blocking，并给出可落地修改建议。
