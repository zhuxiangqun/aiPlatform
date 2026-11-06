# Engineering unfreeze — EVAL G2c（single-annotator self-consistency）

- **decided_at**: `2026-11-02`
- **status**: **Closed PASS**
- **decision**: [`ENGINEERING_DECISION_EVAL_G2C_SELF_CONSISTENCY.md`](./ENGINEERING_DECISION_EVAL_G2C_SELF_CONSISTENCY.md)
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_V1.md`](./ENGINEERING_UNFREEZE_EVAL_V1.md)
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)

## 目标

在 **不开 G2b / 不宣称 accuracy** 的前提下，提供同人二次盲测的 **intra-rater** 一致性：

1. `g2c.py`：对照 G2a adjudicated 标签 vs `g2c_retest` 二次标签 → `intra_rater_kappa` / agreement  
2. API：`GET/POST …/store/g2c-*`（只读状态 + 记录 retest + 计算）  
3. 报告强制：`accuracy_claim=false`；`claim_kind=self_consistency`；κ 字段为 **intra-rater**，禁止写成 inter-annotator  

## 禁止

| 禁止 | 原因 |
|---|---|
| `accuracy_claim=true` / 外部 gate | 决策已降级 |
| 把 self κ 写成「第二标注者 κ」 | 诚实边界 |
| 静默开 G2b | 需独立第二人 |

## 出口

| 项 | 门槛 |
|---|---|
| 单元测试 | kappa 公式 + honesty 字段 |
| API | CoreFacade + store router |
| UI | `/eval?tab=settings` 说明 G2c ≠ accuracy |
| Closeout | `EVAL_V1_G2C_CLOSEOUT.md` |


## Closeout

[`EVAL_V1_G2C_CLOSEOUT.md`](./EVAL_V1_G2C_CLOSEOUT.md)
