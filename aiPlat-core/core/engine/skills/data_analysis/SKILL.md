---
name: data_analysis
display_name: 数据分析
description: 分析结构化/半结构化数据并给出洞察。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: analysis
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
input_schema:
  data:
    type: string
    required: true
  question:
    type: string
    required: false
output_schema:
  insights:
    type: string
---

# 数据分析（Engine）

## SOP
1. 口径澄清：时间范围/指标定义/缺失与异常处理规则。
2. 数据概览：字段、缺失率、分布、异常点。
3. 围绕问题分析并给出“结论-证据-建议”。
