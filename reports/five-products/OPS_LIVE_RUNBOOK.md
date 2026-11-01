# 运维 Live 演练总册（五产品硬门）

> 工程本地/docker 🟨 **不能**替代本册。任何 `*_authorize.sh authorize` 仅在对应 checklist **全部 ✅** 后由运维执行。  
> **预发就绪 Gate**（先于 PG/HA live）：[`ops/STAGING_READY.md`](./ops/STAGING_READY.md) — 未齐则正式 defer，禁止 staging live。  
> **零预算 local staging**（工程验证，非授权）：[`ops/LOCAL_STAGING.md`](./ops/LOCAL_STAGING.md) — `environment=local` / `local-*.json` only。  
> 当前决策：[`ops/LOCAL_DEFER.md`](./ops/LOCAL_DEFER.md)（路径 B · `staging_ready=false` · 下次复审 **2026-11-22**）。  
> 聚合状态（只读）：`bash scripts/ops_live_status.sh`  
> 交接卡（复制粘贴）：[`OPS_HANDOFF.md`](./OPS_HANDOFF.md)  
> 未签脚手架（可选，不授权）：`bash scripts/ops_live_scaffold.sh`

## 硬门总览

| 轨 | 门 | 证据模板 | 记录脚本 | authorize |
|----|----|----------|----------|-----------|
| Central PG/HA | `cutover_authorized` | [`pg_ha/LIVE_DRILL_EVIDENCE.md`](../../packages/aiplat-central/docs/pg_ha/LIVE_DRILL_EVIDENCE.md) | `pg_ha_record_live_drill.sh` | `pg_ha_cutover_authorize.sh` |
| Ontology A3 | `process_split_authorized` | [`ontology/.../LIVE_DRILL_EVIDENCE.md`](../../packages/aiplat-ontology/docs/a3/LIVE_DRILL_EVIDENCE.md) | `a3_record_live_drill.sh` | `a3_split_authorize.sh` |
| Evaluation A3 | `process_split_authorized` | [`evaluation/.../LIVE_DRILL_EVIDENCE.md`](../../packages/aiplat-evaluation/docs/a3/LIVE_DRILL_EVIDENCE.md) | `a3_record_live_drill.sh` | `a3_split_authorize.sh` |
| Pi D3 | `d3_production_authorized` | [`pi/.../LIVE_DRILL_EVIDENCE.md`](../../packages/aiplat-pi-runtime/docs/d3/LIVE_DRILL_EVIDENCE.md) | `d3_record_live_drill.sh` | `d3_authorize.sh` |

## 推荐顺序

1. **PG/HA**（数据面）→ staging 证据 → checklist ✅ → `cutover_authorize`  
2. **Ontology / Eval A3**（拆分）→ 各轨 live → `a3_split_authorize`  
3. **Pi D3**（生产宣称）→ SOC/bundle/N-1 live → `d3_authorize`  

可并行准备证据，但 **authorize 不可跳过 checklist**。

## 每轨固定四步

```text
1) 按 LIVE_DRILL_EVIDENCE 在真实环境演练
2) AIPLAT_LIVE_DRILL_* + *_record_live_drill.sh → drills/live-*.json
3) 将 JSON 的 production_signed 置 true（运维确认）
4) 人工将 checklist 🟨→✅（仅真实完成后）
5) *_authorize.sh status → ready_to_authorize；再 authorize
```

`authorize` **双硬门**：checklist 全 ✅ **且** 最新 `live-*.json` 的 `production_signed=true`（见 `scripts/lib/aiplat_live_evidence.py`）。仅手改 checklist 仍会 REFUSE。

## 禁止

- 用本地/docker 🟨 手改 checklist 为 ✅  
- 未签 live / 未全 ✅ 时跑 `authorize`（脚本会 REFUSE；勿绕过）  
- 未授权即对外宣称切流 / 拆分 / D3 生产就绪  

工程收口：[`ENGINEERING_CLOSEOUT.md`](./ENGINEERING_CLOSEOUT.md) · 状态：[`STATUS.md`](./STATUS.md)
