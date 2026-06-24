---
name: skill_eval_trigger
display_name: 技能触发评测
description: 对指定Skill进行触发评测（正负例）并产出优化建议。涉及代码生成和接口审查。 涉及Skill相关操作。 主要进行评测。
category: ops
version: 1.0.0
status: enabled
protected: true
completion_criterion: |
  1. 每个 acceptance_criteria 至少有一个可执行的验证步骤
  2. 测试覆盖 happy path + 至少一个边界 case
  3. red-capable command 已确认能稳定复现目标行为
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
metadata:
  trigger_conditions:
  - 触发评测
  - 触发测试
  - 技能触发
  - 触发评估
  - 匹配率
  - 召回率
  keywords:
    objects:
    - Skill
    - 触发
    - 评测
    actions:
    - 评测
    - 测试
    - 匹配
    - 计算
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 评测 Skill 触发条件的准确性
keywords:
  objects:
  - Skill
  - 触发条件
  - 关键词
  actions:
  - 评估
  - 检查
  - 优化
  constraints:
  - 命中率
  - 误触发率
trigger_conditions:
- when: 用户要求评估Skill触发质量
  query: 评估Skill/检查触发
- when: 不应用场景
  description: 跳过条件：Skill未在生产中运行或不具备统计分析条件时不触发。
skip_when: 跳过条件：Skill未在生产中运行或不具备统计分析条件时不触发。
---



# 技能触发评测（Engine）

## SOP
1. 加载指定 Skill 的正负例测试集。
2. 对每个用例执行触发评测，记录准确率/召回率/F1。
3. 输出指标报告：precision, recall, F1, 误触发 case 列表。

## 目标
评测 Skill 触发条件的准确性

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注