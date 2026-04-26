---
name: data_analysis
display_name: 数据分析
description: 分析结构化/半结构化数据并给出洞察、结论与可视化建议。
category: analysis
version: 1.0.0
status: enabled
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
trigger_conditions:
  - "分析数据"
  - "看看这个表"
  - "给出洞察"
  - "统计一下"
input_schema:
  data:
    type: string
    required: true
    description: 数据内容（CSV/JSON/文本表格）或数据位置说明
  question:
    type: string
    required: false
    description: 希望回答的具体问题
output_schema:
  insights:
    type: string
    description: 分析洞察
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 数据分析

## 目标
根据数据与问题输出可复用的分析结论（含关键指标、异常点、趋势与建议）。

## 工作流程（SOP）
1. 明确数据口径（时间范围、指标定义、缺失/异常值处理）。
2. 做基础概览：行列数、字段类型、缺失率、重复值、分布。
3. 围绕 `question` 做分析：统计/对比/相关性/分群/趋势。
4. 输出结论：用“结论 → 证据 → 建议”的结构。
5. 给出可视化建议（图表类型 + 轴含义 + 分组方式）。

## 质量要求（Checklist）
- [ ] 口径清楚且不自相矛盾
- [ ] 结论有证据支撑（数字/比例/样本量）
- [ ] 建议可落地
