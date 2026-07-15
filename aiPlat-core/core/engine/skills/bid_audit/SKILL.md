---
name: bid_audit
display_name: 围标串标检测
description: >
  分析投标数据，通过供应商关系图谱检测围标/串标模式。
  检查项：投标价格聚类、供应商关联关系、投标文件相似度、时间窗口重叠度。
category: domain
version: 1.0.0
status: enabled
execution_type: prompt
domain_id: procurement-mvo
triggers:
  - 围标
  - 串标
  - 投标分析
  - 招标合规
  - 供应商关联
  - bid audit
  - 价格异常
permissions:
  - graph:read
  - wiki:read
  - kb:read
effects:
  - type: read
    resources: ["graph:procurement-mvo", "wiki:procurement-mvo"]
    idempotent: true
    rollback_available: false
input_schema:
  purchase_order_id:
    type: string
    required: true
    description: 采购订单ID（如 PO-2025-0089）
  bid_document_id:
    type: string
    required: false
    description: 投标文件ID（如 BID-2025-0103）
output_schema:
  risk_report:
    type: object
    description: 风险报告（risk_level、evidence、scores）
  markdown:
    type: string
    description: 格式化分析报告
trigger_conditions:
  - 用户消息包含围标/串标/投标分析/招标合规等关键词
---

## SOP

### Step 1: 获取投标数据
- 查询指定采购订单的投标供应商列表
- 通过 `sys_graph_traverse` 获取各供应商之间的关联关系（共同股东/关联子公司/历史合作）
- 获取各供应商的投标报价、资质等级、历史中标记录

### Step 2: 供应商关系分析
- 检查投标供应商之间是否存在以下模式：
  - **关联关系**：共同母公司或控股关系
  - **历史合作**：同一项目历史投标记录中的价格模式
  - **人员重叠**：法人/联系人/授权代表重合
- 对每对供应商评估关系强度（0-1）

### Step 3: 价格模式检测
- 价格聚类分析：投标报价是否异常接近（差异 < 3%）
- 报价序位分析：是否存在固定序位模式（A 最高/B 次高/C 最低）
- 参考价偏离：报价与市场参考价的偏差率
- 报价轮次：是否存在多轮报价中的协同行为

### Step 4: 综合评分和报告
- 围标风险评分（0-100）：
  - 关联关系得分：权重 40%（供应商之间有直接关联 +40）
  - 价格模式得分：权重 35%（异常价格聚类 +35）
  - 时间窗口得分：权重 15%（投标时间过于集中 +15）
  - 历史模式得分：权重 10%（历史围标记录 +10）
- 风险分级：低(<30) / 中(30-60) / 高(60-80) / 紧急(>80)
- 输出风险报告：标注具体证据来源

## 输出格式

```markdown
## 围标/串标检测报告

**采购订单**: {po_id}
**投标文件**: {bid_id}
**综合风险评分**: {score}/100 — {risk_level}

### 一、供应商关系分析

| 供应商A | 供应商B | 关联类型 | 关系强度 | 证据 |
|---------|---------|---------|:---:|------|
| {supplier_a} | {supplier_b} | {relation_type} | {strength} | {evidence} |

### 二、价格模式检测

| 检测项 | 结果 | 异常程度 | 证据 |
|--------|------|:---:|------|
| 价格聚类 | {result} | {level} | {evidence} |
| 报价序位 | {result} | {level} | {evidence} |
| 参考价偏离 | {result} | {level} | {evidence} |

### 三、建议

{recommendation}
```

## 反模式 (Anti-patterns)

| ❌ 错误做法 | ✅ 正确做法 |
|---------|---------|
| 不做供应商关系图谱查询直接分析 | Step 1/2 必须通过 sys_graph_traverse 获取供应商关联关系 |
| 只看报价不看关系 | 围标检测的核心是「关系」而非「价格」 |
| 不标注证据来源 | 每个风险项必须附带具体的数据来源和文件引用 |
| 缺少风控建议 | 必须给出下一步操作建议（启动调查/暂停开标/通知监管部门） |
