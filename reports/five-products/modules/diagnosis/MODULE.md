# Diagnosis module（第六能力 · C1–C3）

> **状态**：C1 **PASS** · C2 **PASS** · C3 D2 pack（本地）· `capabilities.manifest`（A0 / D1 cohost）  
> **Charter**：[`diagnosis-v1-charter.md`](../../../../docs/architecture/plans/diagnosis-v1-charter.md)  
> **解冻 / 出口**：[`C1`](../../ops/ENGINEERING_UNFREEZE_DIAGNOSIS_C1.md) · [`C1 closeout`](../../ops/DIAGNOSIS_V1_C1_CLOSEOUT.md) · [`C2`](../../ops/ENGINEERING_UNFREEZE_DIAGNOSIS_C2.md) · [`C2 closeout`](../../ops/DIAGNOSIS_V1_C2_CLOSEOUT.md) · [`C3`](../../ops/ENGINEERING_UNFREEZE_DIAGNOSIS_C3.md)

## 定位

跨平台、证据驱动、可追溯的 AI 运行诊断产品。  
回答「为什么/哪里/证据/怎么办」；**不**回答「好不好」（Evaluation）；**不**自动修复。

## 首发场景

1. run 失败诊断（`run_failure`）  
2. 版本回归诊断（`version_regression`）

## 契约 / 代码

- Evidence / Report schema：[`contracts/schemas/diagnosis_evidence.schema.json`](./contracts/schemas/diagnosis_evidence.schema.json)
- Seed cases：[`../../ops/DIAGNOSIS_V1_C0_SEED_CASES.md`](../../ops/DIAGNOSIS_V1_C0_SEED_CASES.md)
- Fixtures：`packages/aiplat-diagnosis/fixtures/`（≥10 脱敏真实包）
- API：`/api/platform/apps/diagnosis`（`aiPlat-platform/apps/diagnosis`）
- Service：`aiPlat-core/core/apps/diagnosis/service/`
- UI：`/diagnosis`

## 硬边界

- 无 `remediate` / `auto_execute=true`
- `accuracy_claim=false`
- `process_split_authorized=false`
- 旧 `/diagnostics/*` 仍为工程工具箱，不是本产品
