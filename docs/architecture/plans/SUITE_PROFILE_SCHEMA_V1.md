# Suite Profile Schema v1（冻结稿）

> **类型**：契约冻结 / P0 阻塞前置  
> **版本**：`eval.suite_profile.v1` · 2026-11-08  
> **状态**：**Frozen-draft（待 owner 签字后升 Frozen）**  
> **关联**：[`eval-capability-driven-case-pack.md`](./eval-capability-driven-case-pack.md) §6 · [`CAPABILITY_ID_MAP_V1.md`](./CAPABILITY_ID_MAP_V1.md) · ADR §6.1 #4

---

## 0. 冻结元数据

| 字段 | 值 |
|------|-----|
| schema | `eval.suite_profile.v1` |
| owner | _待签：评测方法负责人_ |
| approved_at | _待签_ |
| change_policy | 改配额语义/采样语义 = bump profile schema 或 profile_id |

---

## 1. 定位

**Profile = 一套跑法，不是一套题。**  
同一 Case Bank 可挂多个 Profile（smoke / regression / benchmark）。

- `quotas` 的 key **必须是 canonical_id**（Capability ID Map v1）。  
- `claim_eligible` 默认 `false`；Profile **不得**因档位升高而打开 claim。

---

## 2. 必填字段

| 字段 | 类型 | 约束 |
|------|------|------|
| `schema` | string | 恒为 `eval.suite_profile.v1` |
| `profile_id` | string | 非空；建议 `agent.{smoke\|regression\|benchmark}.vN` |
| `object_type` | string | 如 `agent` |
| `pack_id` | string | 目标 Case Pack |
| `pack_version` | string | 语义化版本 |
| `pack_scope` | string | `global` \| `workspace` \| `tenant`（与创建来源规则一致） |
| `quotas` | object | canonical_id → 正整数；至少 1 个 key |
| `strategy` | string | `all` \| `random` \| `stratified` |
| `seed` | integer \| null | `random`/`stratified` 时建议非 null |
| `claim_eligible` | boolean | **必须 false**（v1） |

条件字段：

| 字段 | 类型 | 何时 |
|------|------|------|
| `workspace_id` | string | `pack_scope=workspace` 必填 |
| `tenant_id` | string | `pack_scope=tenant` 必填 |
| `sample_n` | integer | 可选总上限；与 quotas 冲突时 **fail closed** 或显式 `degraded`（禁止静默改配额） |
| `holdout` | object | 见 §4 |
| `session_group_policy` | object | 见 §3 |
| `on_insufficient` | string | `error`（默认）\| `degraded`；v1 Regression 建议 `error` |
| `min_per_stratum` | integer | stratified 时默认 ≥1 |
| `notes` | string | 可选 |

---

## 3. `session_group` 整组采样

```json
"session_group_policy": {
  "atomic": true,
  "description": "同一 session_group 的 case 必须同进同出 sample_manifest"
}
```

规则：

1. `atomic: true`（v1 **强制**）：采样选中组内任一条 → **整组入选**。  
2. 禁止拆散多轮题（对齐 factory Plan T4）。  
3. 若整组导致超出 quota：按 `on_insufficient` 处理——默认 **error**，不得偷偷丢半组。

---

## 4. Holdout

```json
"holdout": {
  "enabled": false,
  "ratio": 0.0,
  "seed": null,
  "exclude_from_tuning": true
}
```

| 档 | v1 建议 |
|----|---------|
| smoke | `enabled=false` |
| regression | 可选；若启用 `ratio`∈(0,0.3]，且 holdout case 不进调参反馈 |
| benchmark | 建议启用；比例与统计方法 **P2/P4 另批**（不阻塞 schema 冻结） |

Holdout 标记进 manifest 元数据；报告须披露。

---

## 5. Quotas 策略（v1 冻结选择）

**v1：固定每能力配额（fixed），不做风险加权。**

理由：可审、可复现、实现简单。风险加权留到 P2+ 开放问题。

示例（文本可测子集；**不含** A3–A5 / A8 / A9）：

```json
{
  "schema": "eval.suite_profile.v1",
  "profile_id": "agent.regression.v1",
  "object_type": "agent",
  "pack_id": "agent.capability",
  "pack_version": "0.1.0",
  "pack_scope": "global",
  "quotas": {
    "task_completion": 8,
    "clarification": 8,
    "error_recovery": 6,
    "safety": 6,
    "robustness": 6,
    "planning": 5,
    "efficiency": 4,
    "observability": 4
  },
  "strategy": "stratified",
  "seed": 7,
  "session_group_policy": { "atomic": true },
  "holdout": { "enabled": false, "exclude_from_tuning": true },
  "on_insufficient": "error",
  "claim_eligible": false
}
```

Smoke 示例：每核心能力 1–2；Benchmark：配额上调 + holdout 另批。

**禁止**在 v1 Profile quotas 中放入 `tool_selection` / `tool_args` / `tool_result_use` / `multi_turn_memory` / `long_context`，除非同时声明环境就绪；否则编译应拒绝或强制 gap=`unknown`。

---

## 6. 与 Plan 编译输出

Profile 编译必须产出（增量于 Plan v2）：

- `profile_id`
- `sample_manifest`（唯一执行）
- `coverage` / `gaps`（按 canonical）
- `manifest_hash` / `execution_fingerprint`
- pack `scope` + workspace_id/tenant_id

空 manifest / 配额无法满足且 `on_insufficient=error` → **fail closed**。

---

## 7. 验收清单

- [ ] profile_id / quotas / strategy / seed / claim_eligible 字段齐全  
- [ ] session_group atomic 规则写明  
- [ ] holdout 结构存在；smoke 默认关  
- [ ] v1 quotas = fixed（非风险加权）已声明  
- [ ] quotas 不含无环境工具能力（或强制 unknown）  
- [ ] owner 签字  

---

## 8. 签字栏

| 角色 | 签字（`SIGNED suite_profile.v1`） | 日期 |
|------|----------------------------------|------|
| 评测方法负责人 | | |
| 工程负责人（可选） | | |
