# Engineering unfreeze — EVAL **P2-0 Evaluator calibration**

- **decided_at**: `2026-11-06`
- **status**: **Closed** · aggregate + [`EVAL_P2_CALIBRATION_CLOSEOUT_2026-11-06.md`](./EVAL_P2_CALIBRATION_CLOSEOUT_2026-11-06.md)
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_P2.md`](./ENGINEERING_UNFREEZE_EVAL_P2.md)
- **charter**: [`EVAL_P2_CHARTER_2026-11-06.md`](./EVAL_P2_CHARTER_2026-11-06.md)
- **protocol**: [`packages/aiplat-evaluation/docs/a3/CALIBRATION_V0.md`](../../../packages/aiplat-evaluation/docs/a3/CALIBRATION_V0.md)

## 目标

在本地对已有评测结果做**人工抽样复核**（误报 / 漏报 / 与弱代理分歧），产出 `eval.human_calibration.v0` 证据。  
**不**改 composite 权重、**不**翻 `accuracy_claim`、**不**替换 Arena length smoke。

## 允许

| 允许 | 说明 |
|---|---|
| 协议 + 抽查 CSV + 聚合脚本 | `CALIBRATION_V0.md` · `scripts/calibration_*.py` |
| 从已有 G2b / Arena / preference 证据抽样 | 只读证据与 human_pack |
| 人工填表 → 聚合 JSON 入 `docs/a3/evidence/` | claim 恒 false |

## 禁止

| 禁止 | 原因 |
|---|---|
| 自动改 `build_composite` 权重 / gate | 超出本切片 |
| `accuracy_claim=true` | 校准 ≠ accuracy |
| 原标注者自检自己的标签轨 | charter 风险表 |
| 生产默认路径 / process_split | 仍冻 |

## 出口

| 项 | 门槛 |
|---|---|
| 三轨抽查表发出并回收 | G2b · Arena · preference 各 ≥20（或全量若更小） |
| 聚合 `human_calibration_aggregate.v0.json` | `accuracy_claim=false` |
| 方法签字 | 朱莹（方法）· 朱鸿林（QA 抽查）· 朱向群（产品接受） |
| closeout 短页 | `EVAL_P2_CALIBRATION_CLOSEOUT_*.md` |

## 诚实锁

human calibration ≠ accuracy cert · ≠ 自学习写回授权 · 无公网不影响本切片
