---
name: knowledge_retrieval
display_name: 知识召回
description: 从内部知识库召回相关片段。触发条件：用户问"查一下""有没有相关文档""知识库里有什么"。跳过条件：外部网络搜索由 information_search
  处理。 涉及知识相关操作。 主要进行召回。
category: retrieval
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
metadata:
  trigger_conditions:
  - 知识召回
  - 召回
  - 知识检索
  - 相似内容检索
  - 召回文档
  - 相似检索
  - 向量搜索
  keywords:
    objects:
    - 知识
    - 文档片段
    - 向量
    actions:
    - 召回
    - 检索
    - 匹配
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 从内部向量库召回相关文档片段
keywords:
  objects:
  - 知识
  - 文档
  - 页面
  - 条目
  actions:
  - 检索
  - 召回
  - 查询
  - 搜索
  constraints:
  - 相关性
  - 时效性
trigger_conditions:
- when: 用户要求检索知识库
  query: 检索/知识库/召回
- when: 不应用场景
  description: 跳过条件：用户明确指定了外部数据源（非知识库）时不触发。
skip_when: 跳过条件：用户明确指定了外部数据源（非知识库）时不触发。
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

## 目标
从内部向量库召回相关文档片段

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注