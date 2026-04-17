---
name: task_planning
display_name: 任务规划
description: 将目标拆解为可执行的步骤计划（含依赖、验收标准、验证命令）。
category: execution
version: 1.0.0
status: enabled
execution_mode: inline
trigger_conditions:
  - "写个计划"
  - "怎么做"
  - "拆解任务"
  - "实施步骤"
input_schema:
  goal:
    type: string
    required: true
    description: 最终目标
output_schema:
  plan:
    type: string
    description: 分步骤计划
---

# 任务规划

## 目标
把用户目标拆成“照着做就能推进”的步骤，并明确每一步的验收与风险点。

## 工作流程（SOP）
1. 澄清：目标/范围/不做什么/截止时间/验收标准。
2. 分解：按阶段拆成 5-15 个步骤，步骤要可执行（动词开头）。
3. 标注依赖：外部资源、权限、接口、数据。
4. 风险与回滚：列出 1-3 个主要风险及应对。
5. 验证：每个阶段给出验证方式或命令。

## 质量要求（Checklist）
- [ ] 步骤可执行且顺序合理
- [ ] 每阶段有验收点/验证方式
- [ ] 明确依赖与风险
