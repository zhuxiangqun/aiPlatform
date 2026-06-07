---
name: text_generation
display_name: 文本生成
description: 根据提示生成各类文本内容。触发条件：用户要求生成文章、文案、摘要、邮件、对话回复等文本内容。跳过条件：涉及代码生成(code_generation)、数据分析(data_analysis)、翻译(translation)时由对应 Skill 处理。
category: generation
version: 1.0.0
status: enabled
protected: true
execution_mode: prompt
permissions:
- llm:generate
effects:
- type: read
  resources:
  - llm:generate
  idempotent: true
  rollback_available: false
input_schema:
  prompt:
    type: string
    required: true
output_schema:
  text:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
metadata:
  trigger_conditions:
  - 文本生成
  - 写文章
  - 写作
  - 生成文本
  - 写一篇
  - 写报告
  - 起草邮件
  - 撰写文档
  keywords:
    objects:
    - 文本
    - 文章
    - 报告
    - 邮件
    actions:
    - 生成
    - 写作
    - 撰写
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 根据要求生成高质量文本
---

# 文本生成（Engine）

## SOP
1. 明确体裁/语气/长度/受众/语言，不足则询问。
2. 生成：结构清晰，优先要点后正文。
3. 自检：一致性、格式、是否满足约束。

## 目标
根据要求生成高质量文本

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注