# Engineering unfreeze — EVAL G2b **prep**（第二标注者预备）

- **decided_at**: `2026-11-03`
- **status**: **Open (prep only)**
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_V1.md`](./ENGINEERING_UNFREEZE_EVAL_V1.md)
- **prior decision**: [`ENGINEERING_DECISION_EVAL_G2C_SELF_CONSISTENCY.md`](../../ENGINEERING_DECISION_EVAL_G2C_SELF_CONSISTENCY.md)（G2b 曾 defer；本文件只解冻**预备工程**）
- **freeze**: [`ENGINEERING_FREEZE.md`](../../ENGINEERING_FREEZE.md)

## 目标

在 **无 staging / 不宣称 accuracy** 的前提下，准备真正 G2b 所需材料：

1. 30 条盲标任务包（`packages/aiplat-evaluation/docs/a3/g2b_tasks.v0.json`）
2. 标注者 A / B 工作表模板（互不可见）
3. inter-annotator Cohen’s κ 计算脚本（`scripts/g2b_kappa.py`）
4. 操作说明 `G2B_PREP.md`（历史链接失效）

## 允许

| 允许 | 说明 |
|---|---|
| 找第二独立标注者并盲标 | 人工流程；代码只提供包与 κ |
| 计算并报告 `inter_annotator_kappa` | 报告必须 `accuracy_claim=false` 直至独立 closeout |
| 与生产模型 live / B4-S 本地预演并行 | 互不解锁 authorize |

## 禁止

| 禁止 | 原因 |
|---|---|
| `accuracy_claim=true` / 外部 gate | 需独立 G2b closeout + 决策翻牌 |
| 把 G2c intra-rater κ 写成 inter-annotator | 诚实边界 |
| 同人冒充第二标注者 | 违反独立性 |
| `process_split_authorized=true` | 与 G2b 无关；仍冻 |

## 出口（prep）

| 项 | 门槛 |
|---|---|
| 单元测试 | κ 公式 + honesty 字段 |
| 双人盲标完成 | 各 ≥30 条 + 配对报告 JSON |
| accuracy 宣称 | **仍禁止** — 另开 `ENGINEERING_UNFREEZE_EVAL_G2B` closeout |

## 与 G2c 关系

G2c = 同人自洽，已 Closed。
G2b prep = 为**另一人**准备；完成双人盲标前不得宣称 accuracy。
