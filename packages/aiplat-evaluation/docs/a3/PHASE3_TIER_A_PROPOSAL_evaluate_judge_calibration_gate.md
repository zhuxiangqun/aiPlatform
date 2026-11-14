---
doc_type: Reference
---

# Tier A 单符号提案 #1 · `evaluate_judge_calibration_gate`

> 机器：[`evidence/meta_eval/phase3_tier_a_proposal.evaluate_judge_calibration_gate.v0.json`](./evidence/meta_eval/phase3_tier_a_proposal.evaluate_judge_calibration_gate.v0.json)  
> **状态**：`pending_owner_authorize`  
> **诚实锁**：本提案通过 ≠ 产品 `accuracy_claim=true` ≠ 一次全开 19 个 A_candidate

---

## 提案范围（若 owner 接受）

允许将 **`evaluate_judge_calibration_gate`** 记为：

> **scoped Tier A gate（judge calibration / F1）**

含义：

| 允许 | 不允许 |
|---|---|
| 在 F1/META_EVAL 绿前提下，用该函数作 **工程门禁/报告** 的 A 级引用 | 翻转产品级 `accuracy_claim` |
| 仅本符号 `tier_a_gate_authorized=true` | 全局 `tier_a_expansion_authorized=true`（仍 false，或仅「按符号账本」） |
| 继续 `report_only=true` / `claim_eligible=false`（代码内诚实锁） | 打开 L5 / security cert / process_split |

---

## 检查单（预备已齐）

| # | 项 | 证据 |
|---|---|---|
| 1 | 在 A_candidate | [`PHASE3_A_CANDIDATE_INVENTORY.md`](./PHASE3_A_CANDIDATE_INVENTORY.md) |
| 2 | META 家族 F1 绿 | [`META_EVAL_F1_STATUS.md`](./META_EVAL_F1_STATUS.md) · 5/5 |
| 3 | 实现可定位 | `aiPlat-core/core/apps/eval/service/capability_p4_gate.py:33` |
| 4 | 人裁判证据 | `docs/a3/evidence/meta_eval/f1_judge_ratings.human_judge.v0.json` |
| 5 | 代码诚实锁仍在 | `report_only=True` · `claim_eligible=False` · `accuracy_claim=False` |
| 6 | environment | 本地/评测证据；未标 staging |

---

## Owner 决策（请回复其一）

```text
ACCEPT evaluate_judge_calibration_gate scoped Tier A gate
  — 仅本符号；accuracy_claim 仍 false；不扩其余 18 个

REJECT evaluate_judge_calibration_gate
  — 保持全部 unauthorized
```

接受后工程动作（下一回合）：

1. 写入符号账本 `phase3_tier_a_authorized_symbols.v0.json`（仅本符号）  
2. 提案状态 → `accepted`  
3. **不**改 SPLIT / L5 / 产品 accuracy  
4. 再开顺序 #2 提案

---

## 关联

- 扩序：[`PHASE3_TIER_A_EXPAND_ORDER.md`](./PHASE3_TIER_A_EXPAND_ORDER.md)  
- META：[`META_EVAL_STATUS.md`](./META_EVAL_STATUS.md)
