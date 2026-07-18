"""Domain prompts — migrated from harness/utils/prompt_loader.py per CLAUDE.md §17."""

from core.harness.utils.prompt_loader import _register as register_prompt

def register_skills_prompts():
    """Register 1 domain-specific prompts for skills module."""
    prompts = {
        "skill-auto-fill": """你是一个 AI Skill 设计专家。请根据以下需求，设计一个完整的 Skill。

## Skill 名称
${skill_name}

## 功能描述
${description}

## 已有技能（避免重复，功能重叠时复用而非新建）
${skills_catalog}

## 输出格式
输出一个完整的 SKILL.md，包含 YAML frontmatter 和 Markdown SOP。

```yaml
---
name: ${skill_name}
display_name: 中文显示名
description: 一句话描述
category: development|design|analysis|retrieval|document|execution|generation|text|tool|general
version: 1.0.0
status: enabled
skill_kind: rule
permissions: []
trigger_conditions: []
capabilities: [核心能力1, 核心能力2]
input_schema:
  type: object
  properties:
    input:
      type: string
      description: 输入参数
output_schema:
  type: object
  properties:
    result:
      type: string
      description: 输出结果
---
# SOP 标题

## 目标
一行话描述

## 工作流程
1. 第一步
2. 第二步
3. 第三步

## 约束
- 约束1
- 约束2
```

## 要求
1. trigger_conditions 至少 3 个中文触发短语
2. capabilities 至少 2 个，用中文描述核心能力标签
3. input_schema 和 output_schema 用 JSON Schema 格式
4. SOP 用中文写 3-5 个步骤
5. category 必须从给定选项中选一个最匹配的
6. 参考已有技能的 capabilities，避免重复创建功能重叠的技能
7. 只输出 YAML + Markdown，不要任何额外解释""",
    }
    for pid, content in prompts.items():
        register_prompt(pid, content, category="skills")