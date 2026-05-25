---
name: data_analysis
display_name: 数据分析
description: 分析数据并提供洞察。触发条件：用户要求分析数据、统计报表、可视化、找规律。跳过条件：纯代码生成(code_generation)、文档查询(doc_query)时由对应 Skill 处理。
category: analysis
version: 1.0.0
status: enabled
protected: true
execution_mode: prompt
permissions:
  - "llm:generate"
effects:
  - type: read
    resources: ["filesystem:~/.aiplat"]
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
---

# 数据分析（Engine）

## SOP
1. 理解数据格式、规模和目标分析问题。
2. 选择合适的统计/可视化方法并执行。
3. 输出结构化洞察：关键发现、趋势、异常点、建议。
