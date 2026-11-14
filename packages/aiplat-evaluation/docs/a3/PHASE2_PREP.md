---
doc_type: Reference
---

# Phase 2 预备（生产独立 · 未授权）

> 计划 §7 · 沿用 [`SPLIT_CHECKLIST.md`](./SPLIT_CHECKLIST.md) + [`eval-production-independent-service.md`](../../../../docs/architecture/plans/eval-production-independent-service.md)  
> **诚实锁**：本页只做工程盘点；**禁止**宣传「生产独立」；`process_split_authorized` **保持 false**  
> **前置**：Phase 1 已签字（[`PHASE1_AUDIT_WORKSHEET.md`](./PHASE1_AUDIT_WORKSHEET.md)）

---

## 宣传门禁（未齐则禁宣称）

| 条件 | 当前 |
|---|---|
| `process_split_authorized=true`（SPLIT_CHECKLIST 全 ✅） | **false** |
| staging 验收（B4-S） | **blocked**（无独立 staging host） |
| B5 / B6 按清单关闭 | **未关** |
| 环境标签：local 证据不得标 staging | 遵守中 |

---

## SPLIT_CHECKLIST 快照

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| 1 | protocol + healthz | 🟨 本地 | ≠ 授权 |
| 2 | Chart / DB 骨架 | ✅ | |
| 3 | 控制面经 API | ✅ | |
| 4 | 备份恢复 + 回滚 | 🟨 本地 / live 未签 | 须运维 live |
| 5 | ADR 联签 | ✅ 有条件 Accepted | |

---

## 本地可继续（environment=local）

- A1–A6 / B1-L / B2-L 工程与证据刷新  
- B4-S **本机** Docker PG 预演（已有 rehearsal 文档）  
- 不得把上述证据写入 staging 字段或翻转 authorize

## 阻塞（须人/环境）

1. 独立 staging host 确认（[`B4S_PREP.md`](./B4S_PREP.md)）  
2. #4 live 备份/回滚演练签字  
3. 运维执行 authorize 流程（checklist 全 ✅ 之后）

---

## Owner

| 角色 | 动作 |
|---|---|
| 运维 | staging host + live #4 |
| 评测 owner | 保持 authorize=false 直至清单全 ✅ |
| 产品 | 未授权前不对外说「生产独立」 |
