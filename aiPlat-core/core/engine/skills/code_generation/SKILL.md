---
name: code_generation
display_name: 代码生成
description: 根据需求生成代码。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: generation
version: 1.0.0
status: disabled
protected: true
execution_mode: inline
input_schema:
  requirements:
    type: string
    required: true
  language:
    type: string
    required: false
  framework:
    type: string
    required: false
output_schema:
  code:
    type: string
---

# 代码生成（Engine）

> 默认禁用：引擎层按需启用。

## SOP
1. 明确输入输出、边界条件、错误处理与测试策略。
2. 生成可运行的最小实现（MVP），提供运行命令与文件结构。
3. 再补充可维护性（类型/注释/测试）。
