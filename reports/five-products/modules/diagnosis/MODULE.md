# Diagnosis module（第六能力 · C0）

> **状态**：C0 设计中 · 未入 capabilities.manifest  
> **Charter**：[`diagnosis-v1-charter.md`](../../../../docs/architecture/plans/diagnosis-v1-charter.md)

## 定位

跨平台、证据驱动、可追溯的 AI 运行诊断产品。  
回答「为什么/哪里/证据/怎么办」；**不**回答「好不好」（Evaluation）；**不**自动修复。

## 首发场景

1. run 失败诊断  
2. 版本回归诊断  

## 契约

- Evidence / Report schema：[`contracts/schemas/diagnosis_evidence.schema.json`](./contracts/schemas/diagnosis_evidence.schema.json)
- Seed cases：[`../../ops/DIAGNOSIS_V1_C0_SEED_CASES.md`](../../ops/DIAGNOSIS_V1_C0_SEED_CASES.md)

## As-is

- 内部工具箱：`/diagnostics/*` + 管理端 Diagnostics 页面  
- **不是**本产品；C1 起作为证据采集器复用  

## To-be（C1）

- API：`/api/platform/apps/diagnosis`  
- UI：`/diagnosis`  
- Package：`packages/aiplat-diagnosis`（D1c cohost）  
