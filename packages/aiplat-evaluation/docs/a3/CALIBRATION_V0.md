# Human Evaluator Calibration v0（P2-0）

> **Unfreeze**: [`ENGINEERING_UNFREEZE_EVAL_P2_CALIBRATION.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_P2_CALIBRATION.md)  
> **Honesty**: `accuracy_claim=false` · 校准 ≠ 准确率认证 · ≠ 改 composite 默认

## 1. 目的

抽样复核三类已有结果，统计**复核者与原结论不一致**的比例，供后续自学习/门禁设计参考：

| 轨 | 原结论 | 复核问什么 |
|---|---|---|
| G2b | `gold_pass`（模型输出是否达标） | 看 prompt+rubric+model_output，你是否同意 `gold_pass`？ |
| Arena | length winner vs blind gold | length 弱代理与盲评金标是否一致；你更支持哪边？ |
| Preference | 双人 preference 标签 | 你是否同意原 preferred？ |

## 2. 标签

每行必填 `recheck`：

| 值 | 含义 |
|---|---|
| `AGREE` | 同意原结论 |
| `DISAGREE` | 不同意原结论 |
| `UNSURE` | 信息不足 / 边界（尽量少用） |

可选 `notes`。禁止用自由文本代替 `recheck`。

## 3. 抽样（本轮预注册）

| 轨 | n | 规则 |
|---|---:|---|
| G2b | 20 | 10×`gold_pass=true` + 10×`false`（seed 固定） |
| Arena | 20 | 优先 length≠blind 的对；不足再补同意对 |
| Preference | 20 | 自 filled preference 工作表均匀抽样 |

## 4. 角色

| 角色 | 人 | 约束 |
|---|---|---|
| 复核（G2b） | 朱鸿林（QA） | 非原仲裁自嗨；可看 facilitator 证据 |
| 复核（Arena） | 朱莹（方法） | 勿用曾泄漏模型名的 SEND 当依据；看 left/right 文本 |
| 复核（Preference） | 朱向群 或第三人 | 避免只复读自己的旧标签 |
| 汇总 | 工程 | `calibration_aggregate.py` |

## 5. 命令

```bash
cd packages/aiplat-evaluation
python3 scripts/calibration_human_pack.py \
  --out docs/a3/human_pack/calibration \
  --seed 20261106

# 填完 CSV 后：
python3 scripts/calibration_aggregate.py \
  --pack docs/a3/human_pack/calibration/<stamp> \
  --out docs/a3/evidence/human_calibration_aggregate.v0.json
```

## 6. 非目标

≠ 翻 accuracy_claim · ≠ 替换 length smoke · ≠ 自动调权 · ≠ 生产拆分
