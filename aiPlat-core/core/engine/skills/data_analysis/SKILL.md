---
name: data_analysis
display_name: 数据分析
description: 分析数据并提供洞察。触发条件：用户要求分析数据、统计报表、可视化、找规律。跳过条件：纯代码生成(code_generation)、文档查询(doc_query)时由对应
  Skill 处理。
category: analysis
version: 1.0.0
status: enabled
protected: true
completion_criterion: |
  1. 输出符合 ## FILE: 格式规范
  2. 每个文件包含完整可运行代码
  3. 所有依赖项已声明，所有外部引用已校验
execution_mode: prompt
permissions:
- llm:generate
effects:
- type: read
  resources:
  - filesystem:~/.aiplat
  idempotent: true
  rollback_available: false
input_schema:
  data:
    type: string
    required: true
output_schema:
  analysis:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
metadata:
  trigger_conditions:
  - 数据分析
  - 分析数据
  - 统计
  - 数据可视化
  - 数据报告
  - 数据洞察
  - 数据探索
  - 趋势分析
  - 异常检测
  keywords:
    objects:
    - 数据
    - CSV
    - 报告
    - 统计
    actions:
    - 分析
    - 统计
    - 可视化
    - 清洗
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 对数据执行统计分析并输出洞察
keywords:
  objects:
  - 数据
  - CSV
  - Excel
  - JSON
  - 统计
  actions:
  - 分析
  - 统计
  - 可视化
  - 探索
  constraints:
  - 数据格式
  - 样本大小
trigger_conditions:
- when: 用户要求分析数据
  query: 分析/统计/探索数据
- when: 不应用场景
  description: 跳过条件：用户未提供数据来源或数据量极少时不触发。
skip_when: 跳过条件：用户未提供数据来源或数据量极少时不触发。
---



# 数据分析（Engine）

## SOP
1. 理解数据格式、规模和目标分析问题。
2. 选择合适的统计/可视化方法并执行。
3. 输出结构化洞察：关键发现、趋势、异常点、建议。

## 目标
对数据执行统计分析并输出洞察

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注