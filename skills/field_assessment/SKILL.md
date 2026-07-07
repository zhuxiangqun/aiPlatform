---
name: field-assessment
version: 1.0.0
category: fde
execution_type: prompt
description: 客户现场AI落地诊断——输入客户画像, 输出结构化分析报告 (FDE Toolkit B)
input_schema:
  type: object
  properties:
    company_name: {type: string, description: 客户企业名称}
    industry: {type: string, enum: [金融, 制造, 零售, 医疗, 政务, 教育, 科技, 其他]}
    custom_industry: {type: string, description: 若行业不在枚举中, 可自由填写}
    team_size: {type: integer, description: 客户团队规模}
    existing_tech_stack: {type: array, items: {type: string}, description: 现有技术栈}
    data_sources: {type: array, items: {type: string}, description: 数据源类型}
    pain_points: {type: array, items: {type: string}, description: 核心业务痛点}
    compliance_requirements: {type: array, items: {type: string}, description: 合规要求}
    budget_range: {type: string, description: 预算范围}
    timeline: {type: string, description: 预期时间线}
---

# 客户现场AI落地诊断

## 任务
基于客户输入信息, 生成一份完整的AI落地分析报告。

## 分析框架
1. 数据成熟度评估 (结构化/非结构化/数据量/质量)
2. 基础设施适配性 (云端/本地/混合/网络隔离)
3. 业务流程AI增强点识别 (哪些环节可被AI增强)
4. 合规与风险清单 (数据驻留/隐私/审计)
5. 优先级排序的落地方案 (Top 3, 含ROI估算)

## 输出格式

### 1. 摘要 (2-3句话)
### 2. 数据成熟度分析
### 3. 基础设施与部署建议
### 4. AI落地Top 3机会 (按优先级, 含预估ROI)
### 5. 推荐Profile配置 (agent/skill组合)
### 6. 部署路线图 (Day1 / Week1 / Month1)
### 7. 风险清单与缓解措施
