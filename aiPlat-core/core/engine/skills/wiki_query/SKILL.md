---
name: wiki_query
display_name: Wiki 查询
description: 在持久化 Wiki 中搜索知识，沿链接图展开，合成答案。支持输出 Markdown、Mermaid 图表、对比表格。与传统 RAG 不同——知识已由
  LLM 编缉过，交叉链接已存在，查询精度远超向量检索。 主要进行查询。
category: knowledge
version: 1.0.0
status: enabled
execution_mode: prompt
permissions:
- wiki:read
- llm:generate
effects:
- type: read
  resources:
  - filesystem:~/.aiplat/wiki
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
    required: true
    description: 面向人阅读的 Markdown 输出
metadata:
  trigger_conditions:
  - Wiki查询
  - 搜索Wiki
  - 知识库搜索
  - 搜索知识库
  - 查找Wiki
  - 知识检索
  keywords:
    objects:
    - Wiki
    - 知识库
    - 页面
    actions:
    - 查询
    - 搜索
    - 合成
    - 展开
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 搜索 Wiki 并合成答案
protected: true
completion_criterion: |
  1. 所有引用的数据/文档都有具体来源（page/section/line）
  2. 信息不足时明确告知用户，绝不编造
  3. 回答结构清晰，用户无需追问即可执行下一步
keywords:
  objects:
  - Wiki页面
  - 知识条目
  actions:
  - 查询
  - 搜索
  - 浏览
  constraints:
  - 分类
  - 标签
trigger_conditions:
- when: 用户要求查询Wiki
  query: 查Wiki/搜知识库
- when: 不应用场景
  description: 跳过条件：用户未指定搜索范围或不使用Wiki相关术语时不触发。
skip_when: 跳过条件：用户未指定搜索范围或不使用Wiki相关术语时不触发。
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

## 目标
搜索 Wiki 并合成答案

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注