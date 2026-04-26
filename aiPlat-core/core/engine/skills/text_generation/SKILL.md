---
name: text_generation
display_name: 文本生成
description: 根据提示生成各类文本内容。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: generation
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
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
---

# 文本生成（Engine）

## SOP
1. 明确体裁/语气/长度/受众/语言，不足则询问。
2. 生成：结构清晰，优先要点后正文。
3. 自检：一致性、格式、是否满足约束。
