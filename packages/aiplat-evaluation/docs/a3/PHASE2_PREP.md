---
doc_type: Reference
---

# Phase 2 预备（生产独立 · 政策已授 / 运行时未齐）

> 计划 §7 · [`SPLIT_CHECKLIST.md`](./SPLIT_CHECKLIST.md) · staging 板：[`PHASE2_STAGING_PREP.md`](./PHASE2_STAGING_PREP.md)  
> **政策**：`process_split_authorized=true`（owner AUTHORIZE · 覆盖）  
> **运行时**：Chart `a3_process_split_authorized=false` · **禁止**宣称「生产已独立」

---

## 宣传门禁

| 条件 | 当前 |
|---|---|
| 政策 `process_split_authorized` | **true**（owner 覆盖；#1/#4 仍 🟨） |
| Chart runtime split 注解 | **false** |
| staging 验收（B4-S） | **blocked**（脚手架已开 · 无独立 staging host） |
| B4-S staging scaffold | ✅ [`B4S_STAGING_SCAFFOLD.md`](./B4S_STAGING_SCAFFOLD.md) · unfreeze `draft_blocked` |
| 对外「生产已独立」 | **禁止** |
| 环境标签：local ≠ staging | 遵守中 |

---

## SPLIT_CHECKLIST 快照

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| 1 | protocol + healthz | 🟨 本地 | ≠ live |
| 2 | Chart / DB 骨架 | ✅ | Chart split 注解仍 false |
| 3 | 控制面经 API | ✅ | |
| 4 | 备份恢复 + 回滚 | 🟨 本地 / live 未签 | 须运维 live |
| 5 | ADR 联签 | ✅ 有条件 Accepted | |

---

## 本地可继续

- A1–A6 / B1-L / B2-L 证据刷新  
- B4-S **本机** Docker PG 预演（≠ staging）  
- 推进 [`PHASE2_STAGING_PREP.md`](./PHASE2_STAGING_PREP.md) / [`B4S_STAGING_SCAFFOLD.md`](./B4S_STAGING_SCAFFOLD.md) 主机确认清单  

## 阻塞（须人/环境）

1. 独立 staging host（[`B4S_PREP.md`](./B4S_PREP.md)）→ 激活 unfreeze  
2. #4 live 备份/回滚 + `production_signed`  
3. 此后才允许 `a3_split_authorize.sh authorize` 翻 Chart  
