---
name: wiki_lint
display_name: Wiki 健康检查
description: 定期对 Wiki 做健康检查——找出矛盾数据、孤儿页面、死链接、过期内容。LLM 会自动建议补充缺失信息和下一步研究方向。 涉及Wiki相关操作。 主要进行检查。
category: governance
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
  scope:
    type: string
    default: full
    description: full / contradictions / orphans / outdated
output_schema:
  issues:
    type: array
  suggestions:
    type: array
  health_score:
    type: number
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出
metadata:
  trigger_conditions:
  - Wiki检查
  - 知识库健康
  - Wiki健康
  - 文档质量
  - 知识库检测
  - 死链检查
  - Wiki质量
  keywords:
    objects:
    - Wiki
    - 知识库
    - 页面
    actions:
    - 检查
    - 检测
    - 分析
    - 建议
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 检测 Wiki 的矛盾和死链接
---

## SOP

你是 Wiki 健康检查员。定期运行以保持知识库质量。

### 检查维度

**1. Contradictions（矛盾检测）**

调用 `detect_contradictions()` 获取所有标记了矛盾关系的页面对。对每对矛盾：
- 读取两个页面的 body
- 判断矛盾是否仍然存在（可能已被后续编辑解决）
- 如果仍然矛盾：标记为需要解决
- 如果已解决：清除 contradiction 标记

**2. Orphans（孤儿页面）**

找出没有入链但自己有出链的页面。这些页面"只有出去的链接，没有回来的链接"——别人不引用它。
- 建议：添加至少 2 个页面链接到此页面
- 或者：标记为可能需要删除（如果内容过时）

**3. Stale Content（过期内容）**

检查 `last_updated` 超过 90 天未更新的页面。对于每个过期页面：
- 检查 body 是否包含时间敏感的信息（如"2023年"、"最新"、"目前"）
- 如果包含：标记为需要更新
- 建议：用 LLM 搜索最新信息补充

**4. Dead Links（死链接）**

检查 `related` 字段中的链接是否都指向存在的页面。
- 死链接：related 中的页面标题现在不存在 → 需要删除或替换

**5. Research Suggestions（研究方向建议）**

基于当前 wiki 的知识缺口：
- 哪些实体页之间应该有交叉链接但还没有？
- 哪些主题值得创建深度分析页面？
- 建议：输出 3-5 个研究建议

### 输出格式

```json
{
  "health_score": 85,
  "issues": [
    {"type": "contradiction", "page_a": "RAG Benefits", "page_b": "RAG Limitations", "severity": "high"},
    {"type": "orphan", "page": "Quantum ML", "suggestion": "Add links from AI Overview and Future Trends"},
    {"type": "stale", "page": "GPT-4 Capabilities", "last_updated": "2025-01-15", "suggestion": "Update with latest Claude/Gemini comparisons"},
    {"type": "dead_link", "page": "AI Ethics", "dead_target": "EU Regulations 2023", "suggestion": "Replace with EU AI Act 2026"}
  ],
  "suggestions": [
    "Knowledge Graphs 和 Persistent Wiki 之间缺少交叉链接",
    "建议创建 'RAG vs Wiki' 对比分析主题页",
    "LLM Self-Maintenance 话题下缺少实证数据支撑"
  ]
}
```

## 目标
检测 Wiki 的矛盾和死链接

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注