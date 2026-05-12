---
name: data_analysis
display_name: 数据分析
description: 分析数据并提供洞察。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: analysis
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
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
