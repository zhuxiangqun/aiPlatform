---
name: evidence-chain-template
version: 1.0.0
category: validation
description: 基于证据链YAML配置对结论进行溯源验证，输出证据链完整性报告
effects:
  - type: read
    resources: [filesystem:~/.aiplat/evidence, database:logs]
    idempotent: true
input_schema:
  type: object
  properties:
    chain_file:
      type: string
      description: "证据链YAML配置文件路径"
    query_context:
      type: object
      description: "查询上下文 (时间范围、实体ID等)"
output_schema:
  type: object
  properties:
    claim_verification:
      type: array
      description: "每条声明的验证结果"
    hallucination_risk:
      type: number
      description: "幻觉风险评分 0-1"
    confidence:
      type: number
      description: "综合置信度 0-1"
    cross_validation:
      type: object
      description: "多源交叉验证详情"
---

# 证据链模板

## 工作流

1. 加载 `chain_file` YAML — 定义数据源列表 + 验证规则
2. Step 1：多源数据提取（调用 MCP/DB/API 获取原始数据）
3. Step 2：声明提取（`HallucinationTracker` 评估）
4. Step 3：交叉验证（`CrossValidationGate`）
5. Step 4：冲突检测 + 置信度评估

## 链文件格式

```yaml
name: "系统故障诊断"
sources:
  - name: "应用日志"
    type: file
    path: "/var/log/app/error.log"
    parser: "grep_log"
  - name: "Prometheus 指标"
    type: api
    endpoint: "http://prometheus:9090/api/v1/query"
    query: "up{job='aiplat'} == 0"
  - name: "告警记录"
    type: database
    table: "alerts"
    filter: "severity >= 'warning' AND created_at > now() - 1h"
verify:
  min_sources: 2
  contradiction_threshold: 0.3
  graph_cross_check: true
```
