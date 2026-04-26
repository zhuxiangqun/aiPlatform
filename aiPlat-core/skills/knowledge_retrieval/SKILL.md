---
name: knowledge_retrieval
display_name: 知识召回
description: 从向量库/知识库召回相关文档片段，用于辅助回答与决策。
category: retrieval
version: 1.0.0
status: enabled
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
trigger_conditions:
  - "从知识库查"
  - "召回文档"
  - "查内部资料"
input_schema:
  query:
    type: string
    required: true
    description: 查询问题/关键词
output_schema:
  snippets:
    type: string
    description: 召回片段（含引用信息）
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 知识召回

## 目标
从内部知识库召回高相关片段，并输出可引用的证据块。

## 工作流程（SOP）
1. 将 query 转成可检索表达（补同义词、实体）。
2. 召回 Top-K 片段，去重并按相关度排序。
3. 输出每个片段的：标题/来源/片段内容/为什么相关。
4. 给出综合结论（如需要），并引用对应片段编号。

## 质量要求（Checklist）
- [ ] 每个片段含来源信息
- [ ] 召回结果与 query 高相关
