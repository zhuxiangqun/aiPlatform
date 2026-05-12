---
name: skill_eval_trigger
display_name: 技能触发评测
description: 对指定 Skill 进行触发评测（正负例）并产出指标。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
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

# 技能触发评测（Engine）

## SOP
1. 加载指定 Skill 的正负例测试集。
2. 对每个用例执行触发评测，记录准确率/召回率/F1。
3. 输出指标报告：precision, recall, F1, 误触发 case 列表。
