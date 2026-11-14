---
generated_at: 2026-11-14
doc_type: Report
---

# Engineering unfreeze — EVAL_A3 B4-S staging（草稿 · 阻塞）

- **decided_at**: `2026-11-14`
- **status**: **`draft_blocked`** — 独立 staging host **未确认**
- **parent**：[`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](./ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)（本地轨已关）
- **prep**：[`B4S_PREP.md`](../../../packages/aiplat-evaluation/docs/a3/B4S_PREP.md) · [`B4S_STAGING_SCAFFOLD.md`](../../../packages/aiplat-evaluation/docs/a3/B4S_STAGING_SCAFFOLD.md) · [`PHASE2_STAGING_PREP.md`](../../../packages/aiplat-evaluation/docs/a3/PHASE2_STAGING_PREP.md)
- **authorize gate**：`bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh status`（须 `ready_to_authorize=false` 直至 live 签）

## 一句话

本文件是 **B4-S staging 解冻草稿**：允许写脚手架 / 模板 / 看板；**禁止**把本机或虚构主机当成 staging，**禁止** `production_signed`，**禁止**翻 Chart。

## 闸门对照

| 动作 | 本草稿 |
|---|---|
| 写 staging 演练模板 / 看板 / runbook | ✅ |
| 填 `host_id` 等占位字段（仍 `environment=scaffold`） | ✅ |
| 确认真实独立 host 后改 `status` → active | ❌ 须 owner 指名主机后再改 |
| 标 `environment=staging` 且宣称 live | ❌ |
| `production_signed=true` | ❌ |
| `a3_split_authorize.sh authorize` / Chart flip | ❌ |
| 生产 dual-read 回填 | ❌（B4 PITR live 前） |

## 允许的代码面（脚手架期）

- `packages/aiplat-evaluation/docs/a3/`（B4S staging 页、`templates/` 脚手架、prep 板）
- `packages/aiplat-evaluation/scripts/b4s_staging_scaffold_emit.py`
- `reports/five-products/ops/` 本解冻页
- 对应 plan exec 一行

**不允许**：伪造 staging 证据；静默把 checklist #1/#4 🟨 改 ✅；编辑 `chart/Chart.yaml` 的 `a3_process_split_authorized`。

## 证据要求（脚手架）

- 模板 JSON：`environment=scaffold` · `production_signed=false` · `does_not_authorize_process_split=true`
- Chart：`aiplat.a3_process_split_authorized: "false"`
- 政策 `process_split_authorized=true`（owner 已授）≠ Chart runtime

## 退出条件（离开 draft_blocked）

| 结果 | 动作 |
|---|---|
| Owner 指名独立 host（FQDN/集群）+ JWKS/对象存储/PG PITR 可达 | 改本页 `status=active`；填模板；跑 live 演练 |
| live-*.json 为 `environment=staging` 且 `production_signed=true` | 才允许考虑 `a3_split_authorize.sh authorize` |
| 无主机却标 staging / 签名 / 翻 Chart | **停**；撤回越界提交 |

## Honesty

脚手架已开 ≠ staging 验收 ≠ 生产独立宣称。
