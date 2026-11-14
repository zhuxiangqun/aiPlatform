---
doc_type: Reference
---

# META_EVAL_V0 · 元评测最小协议

> 计划 §9 / §4.4 · 阈值签字：[`R11_META_EVAL_THRESHOLDS.md`](./R11_META_EVAL_THRESHOLDS.md)（v0 · 朱向群 · 2026-11-14）  
> Gate 思想：评测评测；**无绿灯不新增 Tier A gate 宣称**  
> Honesty：`accuracy_claim=false` · ≠ process_split · ≠ 准确率认证

---

## 1. 范围

| 在范围 | 不在范围 |
|---|---|
| Judge / gold / contamination / holdout / IAA | 产品级 accuracy 认证 |
| Tier A 扩容前的尺子检查 | 翻转 `process_split_authorized` |
| 与 G2b / preference / arena 人标衔接 | 替代 Phase 1 scorecard |

---

## 2. 五项检查（落地步骤）

### 2.1 Judge calibration

1. 固定人标集（pack 指纹 + seed）；不得边调边改 gold。  
2. 跑 judge → 与人标算 agreement / κ / ECE。  
3. 低于 R11：`agreement≥0.80` / `κ≥0.60` / `ECE≤0.10` → **judge 不得用于 Tier A gate**。  
4. 证据写入 `docs/a3/evidence/meta_eval/`（已建；F1 状态见 [`META_EVAL_F1_STATUS.md`](./META_EVAL_F1_STATUS.md)）。

### 2.2 Gold audit

1. 每季度或每次升 `SCORE_SCOPE` 版本：抽样 ≥ 协议约定条数。  
2. 抽样错误率 > **5%** → **冻结相关宣称**直至仲裁关闭。  
3. 争议必须有裁决记录（谁、何时、结论）。

### 2.3 Contamination

1. 对拟升 Tier A 的题包做与训练/提示/开发集重叠检查。  
2. 超阈 → **advisory only**（R11）；不得写成「已认证无污染」。

### 2.4 Holdout isolation

1. 物理/约定三分：开发 / 验证 / holdout。  
2. CI 只跑开发+验证。  
3. **仅发布前一次揭榜** holdout；揭榜结果入证据，不得回写调参。

### 2.5 Inter-annotator 稳定（IAA）

1. 双人 κ ≥ **0.60**（与 G2b 门槛对齐）。  
2. 漂移超阈 → 重训标注说明 + 重标争议集后再开 gate。

---

## 3. 绿灯定义（Tier A 扩容前置）

```text
对目标能力家族：
  judge calibration 绿 或 显式 advisory_only（不得当硬宣称）
  gold audit 最近一期未超阈
  contamination 已跑（超阈仅 advisory）
  holdout 规则声明在册
  IAA 绿或有豁免+到期日
→ 才允许「新增 Tier A gate 宣称」
```

---

## 4. 变更控制

改任一阈值 = semantic → [`SHA_CHANGE_LOG.md`](./SHA_CHANGE_LOG.md) + bump `meta-eval-thresholds` 版本 + owner 重签。  
协议正文大改 → bump `META_EVAL_V0` → `V1` 并在计划修订记录留痕。

---

## 5. 当前状态（2026-11-14）

| 项 | 状态 |
|---|---|
| 协议成文 | **done**（本文） |
| 阈值 owner 签字 | **done**（R11） |
| 家族清单 | **done**（[`META_EVAL_FAMILY_CHECKLIST_V0.md`](./META_EVAL_FAMILY_CHECKLIST_V0.md)；F1+F4 绿） |
| `evidence/meta_eval/` 实测证据 | **F1+F4 green**（F2/F3 未开；仍 ≠ Tier A 授权） |
| Tier A 扩容 | **blocked**（家族绿 ≠ 扩容授权） |
