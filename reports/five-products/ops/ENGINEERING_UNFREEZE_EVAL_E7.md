# Engineering unfreeze — EVAL_V1 E7（D2/D3 本地收口）

- **decided_at**: `2026-11-01`
- **status**: **Closed — E7 PASS**（[`EVAL_V1_E7_CLOSEOUT.md`](./EVAL_V1_E7_CLOSEOUT.md)）
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_V1.md`](./ENGINEERING_UNFREEZE_EVAL_V1.md) · E6 [`ENGINEERING_UNFREEZE_EVAL_E6.md`](./ENGINEERING_UNFREEZE_EVAL_E6.md)
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **charter**: [`eval-v1-charter.md`](../../../docs/architecture/plans/eval-v1-charter.md) §6 E7 / G4
- **trigger**: E6 PASS（#519）；G2a locked；`packages/aiplat-evaluation` D2 pack 已存在

## 为何选 E7（而非 G2b / Diagnosis C4）

| 选项 | 阻塞 | 结论 |
|---|---|---|
| **EVAL G2b** | 第二标注者 + 100 条 + κ | 暂缓 |
| **Diagnosis C4** | A3 ADR Accept + staging / live | 生产门仍冻 |
| **EVAL E7** | E6 已合入；D2/D3 脚本与基线已就绪 | **本解冻默认路径** |

## 目标

把 EVAL_V1 charter **E7** 收口为可复跑的本地工程证据（**不**升生产 delivery / **不** authorize）：

1. 复跑 `packages/aiplat-evaluation` `d2_local_closeout` + `d3_local_acceptance`
2. 确认 packaging surface / perf baseline / split authorize **REFUSE**
3. 文档：STATUS / FREEZE / MODULE 标注 E7 PASS；`process_split_authorized=false`

## 允许

- `packages/aiplat-evaluation/` 证据 / closeout 刷新
- `reports/five-products/ops/*EVAL*E7*` / STATUS / FREEZE / charter 状态行
- freeze check 锚定 E7 closeout

## 禁止

| 禁止 | 原因 |
|---|---|
| `process_split_authorized=true` / authorize 成功 | 无 live ✅ |
| accuracy / κ / 外部 gate | 需 G2b |
| staging / cutover / A3 生产拆分 | 生产门仍冻 |

## 验证

```bash
bash packages/aiplat-evaluation/scripts/d2_local_closeout.sh
bash packages/aiplat-evaluation/scripts/d3_local_acceptance.sh
bash scripts/check_five_products_packaging_surface.sh
```
