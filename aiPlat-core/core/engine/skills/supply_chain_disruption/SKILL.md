---
name: supply_chain_disruption
display_name: 断供影响评估
description: >
  评估供应链中断（设备故障/物流中断/原材料短缺）的影响范围，
  通过知识图谱多跳遍历找出受影响的下游实体，给出替代方案和风险矩阵。
  适用于产线停机、物流中断、供应商断供等场景。
category: domain
version: 1.0.0
status: enabled
execution_type: prompt
domain_id: supply-chain
triggers:
  - 设备故障
  - 产线停机
  - 断供
  - 物流中断
  - 库存不足
  - 供应商延迟
  - supply chain disruption
permissions:
  - graph:read
  - wiki:read
  - kb:read
effects:
  - type: read
    resources: ["graph:supply-chain", "wiki:supply-chain"]
    idempotent: true
    rollback_available: false
input_schema:
  incident_description:
    type: string
    required: true
    description: 故障/中断的详细描述（设备名称、错误代码、影响描述等）
  affected_entity:
    type: string
    required: false
    description: 已知的受影响实体名称（可选，不填则从描述中提取）
output_schema:
  impact_assessment:
    type: object
    description: 影响评估报告（受影响实体列表、影响工时、风险等级）
  alternative_plans:
    type: array
    description: 替代方案列表
  markdown:
    type: string
    description: 格式化的评估报告
trigger_conditions:
  - 用户消息包含故障/中断/断供/延迟等关键词
---

## SOP

### Step 1: 识别故障实体和图谱上下文
- 从 `incident_description` 中提取故障实体名称（设备、路线、供应商）
- 通过 `sys_graph_traverse` 做 2 跳 BFS 遍历：故障实体 → 1 跳直接关联实体 → 2 跳下游影响实体
- 输出：受影响的实体列表（产线/订单/客户/仓库），标注每跳路径

### Step 2: 评估影响范围和时间
- 计算影响链总长度（跳数）
- 评估高优先级订单是否受影响（priority=high）
- 估算影响工时（以天为单位）：`影响工时 = 关联订单数 × 平均交付周期 / 受影响产线产能`
- 标注风险等级（低/中/高/紧急）：
  - 紧急：影响高优先级订单且无替代方案
  - 高：影响多个订单但存在替代方案
  - 中：影响单个订单且有替代方案
  - 低：影响可忽略或已有预案

### Step 3: 生成替代方案
- 查找替代产能：通过图谱查询同类型产线的 `status=active` 且 `capacity_per_day >= affected_line.capacity_per_day`
- 查找替代物流：查询相同 origin-destination 的 `alternative_routes`
- 查找替代供应商：查询供应同类 Material 且 `tier >= affected_supplier.tier` 的 Supplier
- 每个方案列出：切换成本（时间/费用）、时效（提前或延迟天数）、风险

### Step 4: 输出结构化评估报告
- 摘要段：故障描述 + 影响范围总结 + 推荐方案
- 影响矩阵表格：故障点 | 影响实体 | 影响工时 | 风险等级
- 替代方案表格：方案 | 切换成本 | 时效 | 风险
- 建议段：首选方案 + 理由 + 否决条件

## 输出格式

```markdown
## 供应链中断影响评估

### 影响概览
{incident_description}

| 故障点 | 影响实体 | 影响工时 | 风险等级 |
|--------|---------|---------|---------|
| {entity} | {affected_entity_list} | {hours}d | {risk_level} |

### 替代方案

| 优先级 | 方案 | 切换成本 | 时效变化 | 风险 |
|:---:|------|---------|---------|------|
| 1 | {primary_plan} | {cost} | {time_delta}d | {risk} |
| 2 | {fallback_plan} | {cost} | {time_delta}d | {risk} |

### 建议
{recommendation}
```

## 反模式 (Anti-patterns)

| ❌ 错误做法 | ✅ 正确做法 |
|---------|---------|
| 不查图谱直接凭常识推测影响范围 | Step 1 必须通过 sys_graph_traverse 获取精准影响链 |
| 只列风险不列替代方案 | 每个中断至少给出 1 个替代方案 |
| 忽略多级供应商的牛鞭效应 | 涉及多级供应商时必须评估上游向下的放大效应 |
| 不标注替代方案的否决条件 | 每个方案明确标注什么情况下不可用 |
