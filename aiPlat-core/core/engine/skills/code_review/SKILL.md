---
name: code_review
display_name: 代码审查
description: 审查代码质量并给出改进建议。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: analysis
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
input_schema:
  code:
    type: string
    required: true
  language:
    type: string
output_schema:
  review:
    type: object
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 代码审查（Engine）

## SOP
1. 理解代码意图、上下文和依赖。
2. 按维度审查：正确性、安全性、性能、可维护性、风格。
3. 输出分级问题列表（P0/P1/P2）及改进建议。
