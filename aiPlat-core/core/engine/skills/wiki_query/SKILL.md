---
name: wiki_query
display_name: Wiki 查询
description: 在持久化 Wiki 中搜索知识，沿链接图展开，合成答案。支持输出 Markdown、Mermaid 图表、对比表格。与传统 RAG 不同——知识已由 LLM 编缉过，交叉链接已存在，查询精度远超向量检索。
category: knowledge
version: 1.0.0
status: enabled
execution_mode: prompt
permissions:
  - "wiki:read"
  - "llm:generate"
effects:
  - type: read
    resources: ["filesystem:~/.aiplat/wiki"]
    idempotent: true
    rollback_available: false
input_schema:
  question:
    type: string
    required: true
    description: 用户的自然语言问题
  max_depth:
    type: integer
    default: 2
    description: 链接图展开深度
  output_format:
    type: string
    default: markdown
    description: markdown / mermaid / table
output_schema:
  answer:
    type: string
  sources:
    type: array
  graph_mermaid:
    type: string
  markdown:
    type: string
---

## SOP

你是一个 Wiki 知识查询引擎。与传统 RAG 不同——你搜索的是一个 **LLM 维护的持久化知识库**，里面的页面有人工（LLM）创建的交叉链接、摘药和矛盾标记。

### 查询流程

**1. 搜索匹配页面**

用 `search_pages(query)` 搜索标题和标签匹配的页面。返回前 10 个最相关的 page summary。

**2. 沿链接图展开**

对每个匹配的页面，用 `traverse_links(title, depth)` BFS 展开 1-2 层邻域。这些页面通过 `related` 字段互相关联，是 LLM 编辑时创建的。

**3. 组装上下文**

拼接所有展开页面的 body + summary。注意：
- 如果页面有 `contradictions` 标记，在回答中标注存在争议
- 如果页面有 `source_articles`，引用原始来源

**4. 合成答案**

根据用户要求的 output_format：

| 格式 | 示例 |
|------|------|
| markdown | 标准回答 + 来源引用 |
| mermaid | 输出 Mermaid 图（graph/flowchart） |
| table | Markdown 对比表格 |

### 示例

**用户问**："RAG 的主要局限是什么？"

**Wiki 中已有**：`rag_limitations.md`（related: [vector_search, knowledge_accumulation, durable_memory]）

**展开链接**：traverse_links("RAG Limitations", depth=1) → 展开 vector_search.md, knowledge_accumulation.md, durable_memory.md

**合成答案**：
```markdown
## RAG 的主要局限

根据我们的知识库分析，RAG 存在以下核心局限：

### 1. 知识没有复利
每次查询都是临时拼凑，从不积累。参见 [[durable_memory]]。

### 2. 向量检索对精确词不敏感
用户查询型号或编号时经常漏掉。参见 [[vector_search]]。

### 3. 上下文窗口浪费
top-20 chunks 中有大量噪音。参见 [[knowledge_accumulation]]。
```

### 与 RAG 的关键区别

| RAG | Wiki Query |
|-----|-----------|
| 搜索向量空间中的近邻 | 搜索 LLM 创建的交叉链接 |
| 每次查询从零开始 | 知识已经编缉好 |
| 需要 reranker 去噪 | 链接本身就是高质量筛选 |
| 回答后扔掉 | 好答案存回 wiki |
