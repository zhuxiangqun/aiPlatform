---
name: domain_assessor
display_name: 域匹配评估器
description: 基于客户画像和可用域列表，评估最佳匹配域并输出完整的域名评估报告，包含主域、备选域、不推荐域及详细理由。
version: 2.0.0
category: fde
status: enabled
execution_type: prompt
effects:
  - type: read
    resources: ["~/.aiplat/ontologies/"]
    idempotent: true
    rollback_available: false
input_schema:
  type: object
  properties:
    customer_profile:
      type: object
      description: 客户画像（industry, pain_points, tech_stack等）
    available_domains:
      type: array
      description: 可用域列表
  required:
    - customer_profile
output_schema:
  type: object
  properties:
    markdown:
      type: string
      description: Markdown格式评估报告
    domain_assessment:
      type: object
  required:
    - markdown
---

### SOP 执行指引
1. 读取 customer_profile 的 industry 和 pain_points 字段。
2. 对 available_domains 中每个域进行关键词匹配和语义对齐。
3. 输出三级评估：
   - primary_domain: 最佳匹配域 + confidence(0-1) + match_reasons[]
   - alternatives: 备选域 + 差异分析
   - non_recommended: 不推荐域 + 理由
4. 评估每个域的 maturity、pass_rate、skills_count、wiki_entities。
5. 输出 gap_analysis: 当前域的能力缺口 + 填补成本估计。

### 输出格式
```json
{
  "domain_assessment": {
    "primary_domain": {"name": "...", "confidence": 0.85, "match_reasons": ["...", "..."]},
    "alternatives": [{"name": "...", "reason": "..."}],
    "non_recommended": [{"name": "...", "reason": "..."}],
    "gap_analysis": {"current_gaps": [{"area": "...", "severity": "high"}], "estimated_effort": {"man_days": 10, "complexity": "medium"}}
  }
}
```

### 反模式
- 不要对所有客户推荐同一个域
- 不要忽略 pass_rate 低于 0.7 的域
- 不要忽略 seed_domain 的警告标记
