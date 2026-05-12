---
name: code_generation
display_name: 代码生成
description: 根据需求描述生成代码（## FILE: 格式）。触发条件：用户要求写代码、生成项目、实现功能、修复Bug。跳过条件：纯文本生成(text_generation)、SQL查询(sql相关)、配置修改时由对应 Skill 处理。
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
