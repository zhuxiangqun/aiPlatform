# Engineering unfreeze — DIAGNOSIS C3.5（adversarial / holdout fixture 硬化）

- **decided_at**: `2026-11-02`
- **status**: **Closed PASS**
- **parent**: [`DIAGNOSIS_V1_C3_CLOSEOUT.md`](./DIAGNOSIS_V1_C3_CLOSEOUT.md)
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **owner**: diagnosis（**不扩功能**；只加难例 + 指标子集）

## 目标

C1–C3 在 10 个对齐 fixture 上出现 **1.00** 工程率，不能证明诊断能力。本解冻只加 **adversarial/holdout** 包：

1. ≥6 个 `dx.adv.*` 脱敏 fixture（多根因/误导信号/缺证据硬猜/无 freshness 的 stale 等）
2. `fixture_metrics` 支持 `subset=core|adversarial|all`；**诚实报告** adversarial 率可能 &lt;1.00
3. `accuracy_claim=false` 不变；禁止用 core 1.00 对外宣称准确率

## 禁止

- remediate / A3 / staging / authorize  
- 为抬分而改 gold 对齐引擎  
- 宣称 accuracy  

## 出口

| 项 | 门槛 |
|---|---|
| adversarial fixtures | ≥6 |
| metrics API | 可分别报 core / adversarial |
| honesty | note + `accuracy_claim=false` |
| Closeout | `DIAGNOSIS_V1_C35_CLOSEOUT.md` |
