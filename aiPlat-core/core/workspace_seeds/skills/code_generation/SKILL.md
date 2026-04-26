---
name: code_generation
display_name: 代码生成
description: 根据需求生成代码。应用库默认技能（workspace）：对外可用；生产环境建议白名单/审批后方可调用。
category: generation
version: 1.0.0
status: disabled
protected: false
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
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
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 代码生成（Workspace）

> 默认禁用：对外生成代码通常需要适配团队规范（lint/test/依赖/框架），建议在应用库封装后启用并配合审计。

## SOP
1. 明确输入输出、边界条件、错误处理与测试策略。
2. 生成可运行的最小实现（MVP），提供运行命令与文件结构。
3. 再补充可维护性（类型/注释/测试）。
