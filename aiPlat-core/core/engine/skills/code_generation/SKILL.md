---
name: code_generation
display_name: 代码生成
description: 根据需求描述生成代码。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: generation
uses_code_skill: true
version: 1.0.0
status: disabled
protected: true
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
input_schema:
  requirement:
    type: string
    required: true
output_schema:
  code:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 代码生成（Engine）

## SOP
1. 解析需求：输入语言、框架、代码风格、测试要求。
2. 生成代码：## FILE: 格式，每文件包含完整实现。
3. 自检：语法正确、导入完备、安全无注入。
