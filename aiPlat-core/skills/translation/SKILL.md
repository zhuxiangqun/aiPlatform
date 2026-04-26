---
name: translation
display_name: 多语言翻译
description: 在多语言之间进行翻译，保持术语一致、语气一致，并可选择直译/意译风格。
category: transformation
version: 1.0.0
status: enabled
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
trigger_conditions:
  - "翻译"
  - "翻成中文"
  - "翻成英文"
input_schema:
  text:
    type: string
    required: true
    description: 需要翻译的文本
  target_lang:
    type: string
    required: true
    description: 目标语言（如 zh/en/ja）
output_schema:
  translated:
    type: string
    description: 翻译后的文本
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 多语言翻译

## 目标
准确翻译文本，术语一致，必要时给出多版本（直译/意译/更正式）。

## 工作流程（SOP）
1. 识别领域（技术/法律/营销/日常）与语气要求。
2. 术语处理：
   - 专有名词保留原文或给出括号注释
   - 关键术语保持一致（可附术语表）
3. 输出译文；如原文歧义，标注并给出备选译法。

## 质量要求（Checklist）
- [ ] 不漏译/不增译关键含义
- [ ] 术语一致
