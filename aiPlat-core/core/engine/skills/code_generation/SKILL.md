---
name: code_generation
display_name: 代码生成
description: '根据需求描述生成代码（## FILE: 格式）。触发条件：用户要求写代码、生成项目、实现功能、修复Bug。跳过条件：纯文本生成(text_generation)、SQL查询(sql相关)、配置修改时由对应
  Skill 处理。'
category: generation
uses_file_output: true
version: 1.0.0
status: enabled
protected: true
idempotent: false
completion_criterion: |
  1. 输出符合 ## FILE: 格式规范
  2. 每个文件包含完整可运行代码
  3. 所有依赖项已声明，所有外部引用已校验
execution_mode: handler
execution_type: prompt
triggers:
  - 写代码
  - 实现
  - 编写
  - 生成代码
  - 帮我写
permissions:
- llm:generate
effects:
- type: write
  resources:
  - filesystem:~
  idempotent: false
  rollback_available: true
input_schema:
  requirement:
    type: string
    required: true
output_schema:
  $ref: "code"
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
metadata:
  trigger_conditions:
  - 生成代码
  - 写代码
  - 编写函数
  - 实现功能
  - 代码生成
  - 创建模块
  - 编写程序
  - 写个API
  - 生成类
  - 实现接口
  keywords:
    objects:
    - 代码
    - 函数
    - 类
    - 模块
    actions:
    - 生成
    - 编写
    - 实现
    - 创建
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 根据需求生成高质量可执行代码
sop_flow:
  - "代码生成（Engine）"
  - "解析需求：输入语言、框架、代码风格、测试要求。"
  - "生成代码：## FILE: 格式，每文件包含完整实现。"
  - "自检：语法正确、导入完备、安全无注入。"
  - "根据需求生成高质量可执行代码"
  - "[ ] 输出格式符合规范"
  - "[ ] 正确处理错误和边界条件"
  - "[ ] 返回结果包含引用和来源标注"
keywords:
  objects:
  - 代码
  - 函数
  - 类
  - 模块
  - API
  - 脚本
  - 测试
  actions:
  - 生成
  - 编写
  - 实现
  - 创建
  constraints:
  - 语言
  - 框架
  - 代码规范
trigger_conditions:
- when: 用户要求生成代码
  query: 写代码/实现/创建API/开发
- when: 不应用场景
  description: 跳过条件：用户仅询问概念、对比工具而非实际写代码时不触发。
skip_when: 跳过条件：用户仅询问概念、对比工具而非实际写代码时不触发。
---



# 代码生成（Engine）

## SOP
1. 解析需求：输入语言、框架、代码风格、测试要求。
2. 生成代码：## FILE: 格式，每文件包含完整实现。
3. 自检：语法正确、导入完备、安全无注入。

## 目标
根据需求生成高质量可执行代码

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注