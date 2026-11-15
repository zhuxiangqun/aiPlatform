---
doc_type: Reference
---

# AUTHORIZE process_split

> 机器：[`evidence/meta_eval/phase3_process_split_authorize.v0.json`](./evidence/meta_eval/phase3_process_split_authorize.v0.json)  
> **状态**：`authorized`（朱向群 · 政策覆盖）

## 翻转

| 项 | 值 |
|---|---|
| 政策 `process_split_policy_authorized` | **true** |
| 运行时 `process_split_authorized` | **false**（Checklist / PREP_STATUS 直至 live authorize） |
| Checklist #1 / #4 | 仍 🟨 |
| 独立 staging host | **未确认** |
| Chart `aiplat.a3_process_split_authorized` | **仍 false** |
| 对外「生产已独立」 | **禁止** |

> 命名：政策与运行时**禁止**共用裸字段名。读到 `process_split_authorized: true` 才表示 Checklist/Chart 运行时已翻；政策层只用 `process_split_policy_authorized`。

Chart 翻转须 staging live 证据 + `a3_split_authorize.sh authorize` 运维路径。见 [`PHASE2_STAGING_PREP.md`](./PHASE2_STAGING_PREP.md)。
