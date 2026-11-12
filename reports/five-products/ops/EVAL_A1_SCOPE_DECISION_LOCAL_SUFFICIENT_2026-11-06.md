---
generated_at: 2026-11-11
doc_type: Report
---

# A1 范围决策 — 本地签认足够（2026-11-06）

- **决定**：产品确认**当前阶段以本地 A1 签认为准**；不要求正式 BASE / 生产 A1 pass。
- **本地已签**：[EVAL_A1_DEPLOY_SIGNOFF_local_20261105.md](./EVAL_A1_DEPLOY_SIGNOFF_local_20261105.md) → **pass（仅本地联调）**
- **生产轨**：[ENGINEERING_UNFREEZE_EVAL_A1_PROD.md](./ENGINEERING_UNFREEZE_EVAL_A1_PROD.md) → **Parked**
- **阻塞单**：[`blocked_not_released`](./EVAL_A1_PROD_BLOCKED_NOT_RELEASED_2026-11-05.md) 仍表示「未做生产发布验收」——**不是**工程欠账；无对外宣称「生产已发布」。

## 含义

| 可以说 | 不可以说 |
|---|---|
| 本地联调 A1 已通过 | 生产/公网已发布并通过 A1 |
| UI 联调入口与硬切在本地成立 | CDN/正式主机已验收 |
| 近期不阻塞以本地为准的迭代 | `process_split_authorized=true` |

日后若要对外发布，再解冻生产轨并换正式 BASE 另签。
