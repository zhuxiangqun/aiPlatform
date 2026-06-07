---
name: skill_apply_engine_skill_md_patch
display_name: 应用 Engine Skill 补丁
description: 应用 engine skill 的 SKILL.md 补丁（change-control 治理）。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。 涉及Skill相关操作。 主要进行应用。
category: ops
version: 1.0.0
status: enabled
protected: true
execution_mode: prompt
permissions:
- fs:write
effects:
- type: write
  resources:
  - filesystem:~/.aiplat
  idempotent: true
  rollback_available: false
input_schema:
  skill_id:
    type: string
    required: true
  patch:
    type: string
    required: true
output_schema:
  result:
    type: object
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
metadata:
  trigger_conditions:
  - 技能补丁
  - Skill补丁
  - 应用补丁
  - Skill更新
  - 更新Skill
  - 修复配置
  - 升级版本
  keywords:
    objects:
    - Skill
    - 补丁
    - 配置
    actions:
    - 应用
    - 验证
    - 回滚
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 安全应用 Skill 配置补丁并验证
---

# 应用 Engine Skill 补丁（Engine）

## SOP
1. 校验补丁格式和签名。
2. 对目标 SKILL.md 做安全审计后应用补丁。
3. 输出变更摘要：修改行数、新增字段、风险评估。

## 目标
安全应用 Skill 配置补丁并验证

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注