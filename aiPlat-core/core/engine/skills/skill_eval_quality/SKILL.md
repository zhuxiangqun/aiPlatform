---
name: skill_eval_quality
display_name: 技能质量评测
description: 对指定 Skill 执行质量做评测（用例+规则评分）并产出指标。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: ops
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
input_schema:
  skill_id:
    type: string
    required: true
output_schema:
  metrics:
    type: object
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 技能质量评测（Engine）

## SOP
1. 加载 Skill 的评测用例集和评分规则。
2. 逐用例执行 Skill，按规则维度评分。
3. 输出质量报告：各维度得分、总分、不合格项列表。
