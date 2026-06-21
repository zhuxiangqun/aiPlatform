---
name: skill_eval_quality
display_name: 技能质量评测
description: 对指定Skill执行质量评测（用例+规则评分）并产出指标和报告。涉及代码生成和接口审查。 涉及Skill相关操作。 主要进行评测。
category: ops
version: 1.0.0
status: enabled
protected: true
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
  - 技能评测
  - 质量评测
  - 技能质量
  - 评估技能
  - 质量评估
  - 打分
  - 评测报告
  keywords:
    objects:
    - Skill
    - 评测
    - 指标
    actions:
    - 评测
    - 评估
    - 评分
    - 产出
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 多维度评测 Skill 执行质量
keywords:
  objects:
  - Skill
  - 执行结果
  - 输出质量
  actions:
  - 评估
  - 评分
  - 检查
  constraints:
  - 准确性
  - 完整性
  - 时效性
trigger_conditions:
- when: 用户要求评估Skill质量
  query: 评估质量/检查Skill输出
- when: 不应用场景
  description: 跳过条件：Skill未有足够执行次数（<10）进行统计时不触发。
skip_when: 跳过条件：Skill未有足够执行次数（<10）进行统计时不触发。
---



# 技能质量评测（Engine）

## SOP
1. 加载 Skill 的评测用例集和评分规则。
2. 逐用例执行 Skill，按规则维度评分。
3. 输出质量报告：各维度得分、总分、不合格项列表。

## 目标
多维度评测 Skill 执行质量

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注