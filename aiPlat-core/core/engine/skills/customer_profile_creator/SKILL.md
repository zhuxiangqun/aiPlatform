---
name: customer_profile_creator
display_name: 客户Profile创建
description: 根据客户访谈信息，生成结构化的客户Profile Markdown文档。收集五类信息：客户身份、业务模式、痛点、技术基础、组织与合规。
category: fde
version: 1.0.0
status: enabled
execution_type: handler
triggers: [客户信息, 客户Profile, 业务认知]
effects:
  - type: read
    resources: ["wiki:default", "graph:default"]
    idempotent: true
    rollback_available: false
input_schema:
  interview_notes: { type: string, required: true, description: 客户访谈原始记录 }
  industry_hint: { type: string, required: false }
  deployment_mode: { type: string, required: false, enum: [online, airgap, hybrid] }
output_schema:
  customer_profile: { type: object }
  markdown: { type: string }
---

## SOP

### Step 1: 读取访谈记录
- 从 `interview_notes` 中提取关键信息：企业名称、行业、业务模式描述、团队规模
- 标注信息缺失点——哪些五类中还没有覆盖

### Step 2: 结构化输出
- 按五类整理：身份/模式/痛点/技术/组织
- 每类用 `## 二级标题` 分隔
- 缺失字段留空，标注 `[待补充]`
- 不要编造信息——宁可留空也不要猜想

### Step 3: 追问缺失
- 如果五类中有超过 2 类信息缺失 → 返回追问列表
- 如果信息基本齐全 → 生成完整的客户 Profile Markdown

## 输出格式

```markdown
## 客户身份
- 企业名称: ...
- 行业: ...
- 团队规模: ...

## 业务模式
- 核心业务: ...
- 关键流程: ...

## 痛点
- 痛点1: ...
- 痛点2: ...

## 技术基础
- 技术栈: ...
- 数据源: ...

## 组织与合规
- 决策链: ...
- 合规要求: ...
- 部署模式: ...
```

## 反模式

| 错误 | 正确 |
|------|------|
| 信息不足时自己编造 | 标注 `[待补充]`，询问客户 |
| 跳过组织与合规部分 | 这是 FDE 推进的关键信息 |
