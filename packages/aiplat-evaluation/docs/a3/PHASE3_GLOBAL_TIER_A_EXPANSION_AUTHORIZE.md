---
doc_type: Reference
---

# Phase 3 · 全局 Tier A 扩容授权

> 机器：[`evidence/meta_eval/phase3_global_tier_a_expansion_authorize.v0.json`](./evidence/meta_eval/phase3_global_tier_a_expansion_authorize.v0.json)  
> **状态**：`authorized`（朱向群 · `AUTHORIZE global_tier_a_expansion`） · 2026-11-14T22:02:00+08:00

## 翻转

| 旗标 | 新值 |
|---|---|
| `global_tier_a_expansion_authorized` | **true** |

## 仍为 false（须另授）

| 旗标 | 值 |
|---|---|
| `accuracy_claim` | false |
| `l5_declare_authorized` | false |
| `security_certification` | false |
| `process_split_authorized` | false |
| Tier B 覆盖完成宣称 | false |
| 单一覆盖% | 禁止 |

## 范围

- 允许：对账本内 **19** 个 A_candidate 符号作 Tier A gate 扩容引用（META 家族仍须绿）  
- 禁止自动：新增第 20 个 A_candidate、产品准确率认证、L5 declare、security cert、process_split、单一覆盖%

账本：[`PHASE3_TIER_A_AUTHORIZED.md`](./PHASE3_TIER_A_AUTHORIZED.md)
