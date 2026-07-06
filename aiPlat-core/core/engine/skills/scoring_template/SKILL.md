---
name: scoring-engine-template
version: 1.0.0
category: evaluation
effects:
  - type: read
    resources: [filesystem:~/.aiplat/scoring]
    idempotent: true
input_schema:
  type: object
  properties:
    rule_file:
      type: string
      description: "YAML 评分规则文件路径"
    target_data:
      type: object
      description: "待评分的业务数据 (dict)"
output_schema:
  type: object
  properties:
    scores:
      type: object
      description: "各维度得分"
    overall:
      type: number
      description: "综合得分 0-100"
    verdict:
      type: string
      enum: [pass, warn, fail]
---

# 评分引擎模板

## 工作流

1. 从 `params.rule_file` 加载 YAML 评分规则
2. 从 `params.target_data` 提取待评分字段
3. 调用 `core.harness.evaluation.dimensions.get_scoring_dimensions()` + `compute_overall_score()`
4. 逐维度计算 → 综合分 → 返回结构化报告

## 规则文件格式

```yaml
name: "客户商机评分"
dimensions:
  - name: "预算匹配度"
    weight: 0.35
    thresholds: {high: 80, medium: 50, low: 30}
  - name: "决策链完整度"
    weight: 0.25
    thresholds: {high: 90, medium: 60}
  - name: "竞品替代风险"
    weight: 0.20
    type: reverse
  - name: "历史成交率"
    weight: 0.20
verdict:
  pass: {min: 70}
  warn: {min: 50}
  fail: {max: 49}
```
