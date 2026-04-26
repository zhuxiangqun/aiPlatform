---
name: code_generation
display_name: 代码生成
description: 根据需求描述生成代码（支持指定语言/框架/目录结构），并给出可运行的最小实现。
category: generation
version: 1.0.0
status: disabled
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
trigger_conditions:
  - "写代码"
  - "生成代码"
  - "实现一个"
  - "给我一段示例代码"
input_schema:
  requirements:
    type: string
    required: true
    description: 功能需求与约束
  language:
    type: string
    required: false
    description: 编程语言（如 python/typescript/go）
  framework:
    type: string
    required: false
    description: 框架（如 fastapi/react/spring）
output_schema:
  code:
    type: string
    description: 生成的代码（或补丁说明）
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 代码生成

> 默认禁用：请在管理面启用后使用。

## 目标
将 `requirements` 转换为可运行的最小实现，并保持可读性与可扩展性。

## 工作流程（SOP）
1. 明确输入输出、边界条件、错误处理、测试策略。
2. 选择语言/框架（如未指定，给 1-2 个推荐并说明取舍）。
3. 生成最小可运行版本（MVP），优先保证可跑通。
4. 补充必要的注释、类型、异常处理与基础测试用例。
5. 输出代码与运行方式；如涉及多文件，提供文件树与关键文件内容。

## 质量要求（Checklist）
- [ ] 可运行/可编译（给出运行命令）
- [ ] 关键错误处理完善
- [ ] 不引入多余复杂度（先 MVP 再增强）
