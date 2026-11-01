# Engineering decision — EVAL claim 降级为 G2c（self-consistency）

- **decided_at**: `2026-11-02`
- **status**: **Accepted**
- **decider**: product owner（对话确认：「把 claim 降级为 self-consistency」）
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_V1.md`](./ENGINEERING_UNFREEZE_EVAL_V1.md) · charter [`eval-v1-charter.md`](../../../docs/architecture/plans/eval-v1-charter.md)

## 决策

**不启动 G2b**（第二独立标注者 + inter-annotator κ + accuracy claim）。  
可选后续工程校准命名为 **G2c：single-annotator test-retest（self-consistency）**。

| 允许 | 禁止 |
|---|---|
| 同人盲测重测 → **intra-rater** 一致率 / κ | 写成「第二标注者」或 inter-annotator κ |
| judge 校准、确定性检查、工程 gate | `accuracy_claim=true` / 外部 gate 宣称 |
| 继续 G2a local `gate_claim` | 用 self-consistency 冒充 accuracy |

**一句话**：可以当唯一标注者，但不能同时当第二标注者；claim 降级为自我一致性。

## 与 G2a / G2b 关系

| 档位 | 现状 |
|---|---|
| **G2a** | **PASS**（30 条 solo；`accuracy_claim=false`；κ=null） |
| **G2b** | **Defer** — 无独立第二人则不开 |
| **G2c** | **Accepted as optional track** — 若做，须新 unfreeze；报告必须写 `self-consistency, not accuracy` |

## 触发 G2c 实现时（另批）

1. 新 `ENGINEERING_UNFREEZE_EVAL_G2C.md`（不静默扩大）  
2. 盲测：打乱 + 间隔 ≥1 周 + 同人二次标注  
3. 报告字段：`intra_rater_kappa` / `self_consistency`；**永不**设 `accuracy_claim=true`  
4. UI 诚实横幅保留「非准确率认证」

## 非目标

- 找第二标注者（留给将来若要真正 G2b）  
- Diagnosis C4 / staging  
- 用 fixture Top-1=1.00 宣称诊断准确率  
