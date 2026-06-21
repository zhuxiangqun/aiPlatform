---
name: root_cause_analysis
display_name: 根因分析
description: 根据测试失败输出，分析失败根因并给出修复建议。触发条件：测试未通过时。跳过条件：测试全部通过。 涉及故障相关操作。 主要进行分析。
category: quality
version: 1.0.0
status: enabled
execution_mode: prompt
permissions:
- fs:read
effects:
- type: read
  resources:
  - filesystem:~
  idempotent: true
  rollback_available: false
input_schema:
  test_report:
    type: object
    required: true
output_schema:
  analysis:
    type: object
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出
metadata:
  trigger_conditions:
  - 根因分析
  - 根本原因
  - 原因分析
  - 故障排查
  - 问题定位
  - 故障诊断
  - 错误分析
  - 问题排查
  keywords:
    objects:
    - 故障
    - 错误
    - bug
    - 日志
    actions:
    - 分析
    - 排查
    - 定位
    - 诊断
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 追溯故障根因并给出修复建议
protected: true
keywords:
  objects:
  - 问题
  - 故障
  - 异常
  - Bug
  actions:
  - 分析
  - 排查
  - 定位
  - 诊断
  constraints:
  - 根因
  - 影响范围
  - 复现步骤
trigger_conditions:
- when: 用户要求定位问题根因
  query: 排查/根因分析/定位问题
- when: 不应用场景
  description: 跳过条件：问题已明确定位且有明确解决方案时不触发。
skip_when: 跳过条件：问题已明确定位且有明确解决方案时不触发。
---



# 根因分析（Engine）

## SOP
1. 读取 test_report 中的 failed cases 和 issues。
2. 按错误模式分类：代码逻辑错误、配置错误、环境问题、安全违规。
3. 对每类失败给出根因+建议修复方向。
4. 输出结构化分析报告（root_causes + fix_suggestions）。

## 目标
追溯故障根因并给出修复建议

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注