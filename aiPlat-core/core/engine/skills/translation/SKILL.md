---
name: translation
display_name: 多语言翻译
description: 多语言翻译，保持术语一致与语气一致。触发条件：用户要求翻译、转换语言、中译英、英译中。跳过条件：纯代码生成或数据分析时由对应 Skill 处理。
category: transformation
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
  text:
    type: string
    required: true
  target_lang:
    type: string
    required: true
output_schema:
  translated:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
metadata:
  trigger_conditions:
  - 翻译
  - 多语言
  - translate
  - 中日韩翻译
  - 中译英
  - 英译中
  keywords:
    objects:
    - 文本
    - 文档
    - 句子
    - 代码
    actions:
    - 翻译
    - translate
    - 本地化
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 在多语言间准确翻译保持术语一致
---

# 多语言翻译（Engine）

## SOP
1. 判断领域与语气要求，必要时构建术语表。
2. 翻译并保证术语一致；歧义给出备选译法。
3. 输出译文（可选：直译/意译/更正式版本）。

## 目标
在多语言间准确翻译保持术语一致

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注