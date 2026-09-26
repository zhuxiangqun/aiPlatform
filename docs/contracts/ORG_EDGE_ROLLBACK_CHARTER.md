# E 波 Charter — 仲裁边回滚（先契约，不是 M4）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-EDGE-ROLLBACK-CHARTER-2026-09` |
| 版本 | **v1.0**（E0 契约） |
| 日期 | 2026-09-19 |
| 状态 | ☑ **E0–E2** · ☐ 不称 M4/L5 |
| 关联 | [`ORG_V_WAVE_CHARTER.md`](./ORG_V_WAVE_CHARTER.md) §6 · [`ORG_K_WAVE_CHARTER.md`](./ORG_K_WAVE_CHARTER.md) F1 · [`ORG_L5_DECISION_RECORD.md`](./ORG_L5_DECISION_RECORD.md) §8 |
| 决策 | D-E1–D-E6 |

**纪律**：E2 已落地。只撤回带 `edge_before` 的 merge 边。不打开 `m4_claim_allowed`。不回滚活 YAML。不生成 `SKILL.md`。不拉起舰队。不开第二域、第二入站渠道。

---

## 0. 一句话

以后只能撤回「已批准的 merge 单，经 `apply_ticket` 写下、且单上留有写入前快照」的那一对跨域标记。没有快照的旧边，不能假装撤掉。

---

## 1. 代码事实（2026-09-19）

| # | 事实 | 证据 |
|---|------|------|
| F-E1 | 生产写边只走 `apply_ticket`。`status=approved` 且 `decision=merge` 才调用 `CrossDomainResolver.resolve`。`decision=add` 不写边 | `k_wave_arbit.py` `apply_ticket` |
| F-E2 | `resolve` 在左右两个图的实体 `metadata["_cross_domain"]` 上各写一份。`add_entity_property` 整键覆盖，不保留旧值 | `resolver.py` `resolve`；`graph_index.py` `add_entity_property` |
| F-E3 | 自 E1 起，`apply_ticket` 在调用 `resolve` 之前把两侧旧值写入 `edge_before` 并落盘。读图失败则不调用 `resolve`。E1 之前的旧单没有这份字段 | `k_wave_arbit.py` `_capture_edge_before` |
| F-E4 | `rollback_proposal` 只恢复活 YAML。它不读、不改 `_cross_domain` | `versioned_ontology_store.py` `rollback_proposal` |
| F-E5 | V5 范围接口把「仲裁 apply 经 `resolve()` 写下的边」列在不可回滚 | `k_wave_rollback.py` `rollback_scope` |
| F-E6 | `apply` 路由的操作者来自请求体 `actor`，不是 `X-AIPLAT-ROLE`。本波不顺手改这条旧路由的身份 | `extraction_routes.py` `apply_arbitration_ticket` |

`_cross_domain` 是一个对象，不是列表。后一次 merge 会盖掉同一实体上的前一次标记，图里没有历史。

---

## 2. 能撤 / 不能撤

| 能撤（E2 之后，且仅当快照在） | 不能撤 |
|------------------------------|--------|
| 该单 `decision=merge`，`edge_written=true`，单上有 `edge_before`，且当前两侧 `_cross_domain` 仍指向这张单的对端 | 已写下但没有 `edge_before` 的旧边 |
| | `decision=add` / `reject` / `defer` / `conflict` |
| | 活 YAML、`draft_local_*`、`k5_local_*`、没有提案 id 的案例 |
| | `rollback_proposal` 能撤的本体提案（那条路保持原样，不合并） |
| | 被后一张单盖掉的边（当前标记已经不是这张单） |
| | 不是这张单写下的 `_cross_domain` |

禁止「一键撤回任意变更」。禁止在没有快照时删掉 `_cross_domain` 凑数。

---

## 3. 快照（E1，先于撤回）

E1 只加快照，不提供撤回接口。

在调用 `resolve` 之前，把左右实体当前的 `_cross_domain` 读出来（没有则记 `null`），写入该仲裁单的 `edge_before`。然后才调用现有 `resolve`。失败则不把单标成 `edge_written`。

已存在的单不回填快照。

---

## 4. 撤回（E2，在 E1 之后）

1. 只接受一张单。两侧一起恢复到 `edge_before`：当时是 `null` 就去掉这个键，当时有值就写回那个值。一侧失败则两侧都不改。
2. 若当前任一侧的 `target_id` 已经不是这张单的对端，拒绝，原因 `edge_superseded`。不自动顺着链条往前撤。
3. 没有 `edge_before`，拒绝，原因 `edge_before_missing`。
4. 成功后：`edge_rolled_back=true`，`edge_written=false`。同一张单不得再次 `apply`。要对齐，另开一张单。
5. 不调用 `rollback_proposal`，不写活 YAML，不改 `VersionedOntologyStore`。
6. 新路由的身份只认 `X-AIPLAT-ROLE`。空身份拒绝。沿用已有角色，不新建角色名。允许与否只判决一次。请求体里的 `actor` 不是授权。
7. E2 落地后，`GET …/org/rollback/scope` 把「带快照的 merge 边」从不可回滚改到可回滚。没有快照的边留在不可回滚。在 E2 之前，该接口文案不得提前改口。

---

## 5. 非目标

不做：客户签收、把 `m4_claim_allowed` 设为 true、第二域、第二入站渠道、自动生成 `SKILL.md`、舰队多 Agent、删除 `AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY`、扩大到活 YAML、修复旧 `apply` 路由的 body 身份、回填历史快照。

---

## 6. 阶段

| 阶段 | 内容 | 本文件状态 |
|------|------|------------|
| E0 | 本文 + Decision Record §8 | ☑ 2026-09-19 |
| E1 | `apply_ticket` 写入前保存 `edge_before`。无撤回接口 | ☑ **2026-09-19** 缺实体记 null；读图失败则不调用 `resolve` |
| E2 | 按 §4 撤回。然后才改范围接口的两列 | ☑ **2026-09-19** `POST …/tickets/{id}/rollback-edge`；身份只认 `X-AIPLAT-ROLE` |

---

## 7. 宣布用语

> E 波 E2 于 2026-09-19 落地：一张带 `edge_before` 的 merge 单可以两侧一起撤回。没有快照、或已被后一张单盖掉的边，拒绝。不写活 YAML。这不是 M4，也不是 L5。
