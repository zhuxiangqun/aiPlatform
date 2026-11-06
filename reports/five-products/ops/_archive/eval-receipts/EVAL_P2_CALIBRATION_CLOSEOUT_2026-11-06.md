# EVAL P2-0 — Human calibration closeout（2026-11-06）

- **status**: **PASS（工程校准）** · `accuracy_claim=false`
- **unfreeze**: [`ENGINEERING_UNFREEZE_EVAL_P2_CALIBRATION.md`](./ENGINEERING_UNFREEZE_EVAL_P2_CALIBRATION.md)
- **protocol**: [`CALIBRATION_V0.md`](../../../packages/aiplat-evaluation/docs/a3/CALIBRATION_V0.md)
- **aggregate**: [`human_calibration_aggregate.v0.json`](../../../packages/aiplat-evaluation/docs/a3/evidence/human_calibration_aggregate.v0.json)
- **pack**: `human_pack/calibration/20261105T161330Z`（gitignore；桌面收回）

## 结果（n=60）

| 轨 | n | AGREE | DISAGREE | UNSURE | disagree_rate |
|---|---:|---:|---:|---:|---:|
| G2b（朱鸿林） | 20 | 19 | 0 | 1 | 0.00 |
| Arena（朱莹） | 20 | 11 | 9 | 0 | 0.45 |
| Preference（朱向群） | 20 | 13 | 7 | 0 | 0.35 |
| **overall** | **60** | **43** | **16** | **1** | **0.2667** |

## 读法（诚实锁）

- 不一致率 ≠ accuracy；≠ 改 composite；≠ 翻 claim。
- G2b 与裁决金标高度一致（1×UNSURE：efficiency family 口径）。
- Arena 45% DISAGREE：复核偏向**更短/更正确**侧，多次与 `blind_gold` 冲突 → length smoke **不可**升格；盲金本身也需复查（仲裁 vs 盲金漂移）。
- Preference 35% DISAGREE：原 preferred 在安全/运维语义题上有偏；供 P2-3 自学习抗性参考，不自动写回。

## 出口核对

| 项 | 状态 |
|---|---|
| 三轨 ≥20 收回 | ✅ |
| aggregate `accuracy_claim=false` | ✅ |
| 方法/QA/产品签字（填表即签） | ✅ 鸿林·莹·向群 |
| 禁止改权重 / length 默认 | ✅ 未改 |

## 下一步（非本切片）

P2-1 上下文基准可开工（复用抽样方法）；P2-3 自学习抗性仍依赖本校准结论作风险输入，不自动授权写回。
