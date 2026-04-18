---
name: data_analysis
display_name: 数据分析
description: 分析结构化/半结构化数据并给出洞察。应用库默认技能（workspace）：对外可用；数据来源需合规并建议脱敏。
category: analysis
version: 1.0.0
status: enabled
protected: false
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

# 数据分析（Workspace）

## SOP
1. 口径澄清：时间范围/指标定义/缺失与异常处理规则。
2. 数据概览：字段、缺失率、分布、异常点。
3. 围绕问题分析并给出“结论-证据-建议”。

