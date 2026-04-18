---
name: translation
display_name: 多语言翻译
description: 多语言翻译，保持术语一致与语气一致。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: transformation
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
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
---

# 多语言翻译（Engine）

## SOP
1. 判断领域与语气要求，必要时构建术语表。
2. 翻译并保证术语一致；歧义给出备选译法。
3. 输出译文（可选：直译/意译/更正式版本）。
