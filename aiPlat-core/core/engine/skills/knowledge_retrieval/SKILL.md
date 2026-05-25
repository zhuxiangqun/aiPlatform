---
name: knowledge_retrieval
display_name: 知识召回
description: 从内部知识库召回相关片段。触发条件：用户问"查一下""有没有相关文档""知识库里有什么"。跳过条件：外部网络搜索由 information_search 处理。
category: retrieval
version: 1.0.0
status: enabled
protected: true
execution_mode: prompt
permissions:
  - "llm:generate"
effects:
  - type: read
    resources: ["filesystem:~/.aiplat"]
    idempotent: true
    rollback_available: false
input_schema:
  query:
    type: string
    required: true
output_schema:
  snippets:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 知识召回（Engine）

## SOP
1. 规范化 query（补实体/同义词，查询改写已由 ReActLoop hook 自动处理）。
2. 召回 Top-K，去重并排序（混合检索 + 多因子重排 + CRAG 质量门已由 KnowledgeRetriever 自动处理）。
3. 基于检索到的片段生成回答。

## 回答规则（必须严格遵守）
- 只根据提供的【已知信息】回答。
- 如果已知信息中没有相关内容，直接回复"暂时无法回答这个问题"。
- 不要编造事实、不要猜测、不要补充未在片段中出现的信息。
- 回答末尾列出信息来源（doc_id 或片段编号）。

## 输出格式
```markdown
## 回答
[基于已知信息的回答内容]

## 信息来源
- [来源1]
- [来源2]
```
