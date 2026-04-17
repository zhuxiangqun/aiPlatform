---
name: text_generation
display_name: 文本生成
description: 根据提示生成各类文本内容（摘要、改写、邮件、说明文档等）。
category: generation
version: 1.0.0
status: enabled
execution_mode: inline
trigger_conditions:
  - "生成文本"
  - "写一段"
  - "帮我改写"
  - "写邮件"
input_schema:
  prompt:
    type: string
    required: true
    description: 生成内容的需求描述/提示词
output_schema:
  text:
    type: string
    description: 生成的文本内容
---

# 文本生成

## 目标
根据输入 `prompt` 生成符合要求的文本内容，并保证结构清晰、表达准确。

## 工作流程（SOP）
1. 复述并确认生成目标（体裁/语气/长度/受众/语言）。
2. 若信息不足，提出 1-3 个关键澄清问题（优先用选项）。
3. 生成文本：先给结构/大纲，再给正文（或按用户要求直接给正文）。
4. 自检：事实一致性、语气、格式、是否满足长度与约束。
5. 输出最终文本；如适用附上可选改进版本（精简/正式/口语）。

## 质量要求（Checklist）
- [ ] 内容与用户目标一致
- [ ] 结构清晰（标题/要点/段落）
- [ ] 无明显语病与重复
