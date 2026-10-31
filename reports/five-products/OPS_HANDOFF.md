# 运维交接卡（Live → Authorize）

> 只读状态：`bash scripts/ops_live_status.sh` · JSON：`bash scripts/ops_live_status.sh --json`  
> 未签脚手架（可选）：`bash scripts/ops_live_scaffold.sh`  
> 总册：[`OPS_LIVE_RUNBOOK.md`](./OPS_LIVE_RUNBOOK.md)

## 当前快照（工程侧 · 未授权）

| 轨 | checklist | live signed | ready_to_authorize |
|----|-----------|:-----------:|:------------------:|
| PG/HA | 1–4·7 🟨 · 5–6 ✅ | false | false |
| Ontology A3 | 1·3·5 🟨 · 2·4·6 ✅ | false | false |
| Evaluation A3 | 1·4 🟨 · 2·3·5 ✅ | false | false |
| Pi D3 | 3–6 🟨 · 1·2·7·8 ✅ | false | false |

刷新：`bash scripts/ops_live_status.sh --json`

## 公共环境

```bash
export AIPLAT_LIVE_DRILL_ENV=staging   # 或 prod-canary；禁止用 scaffold 冒充
export AIPLAT_LIVE_DRILL_OPERATOR=$USER
```

## 第一刀：PG/HA（推荐先做）

> **当前决策：路径 B — 正式 defer（四轨）** — `staging_ready=false`；只跑 local/docker rehearsal（🟨），不签 live、不 authorize。  
> 见 [`ops/LOCAL_DEFER.md`](./ops/LOCAL_DEFER.md) · [`ops/PGHA_LIVE_RUNLOG.md`](./ops/PGHA_LIVE_RUNLOG.md) · [`ops/STAGING_READY.md`](./ops/STAGING_READY.md)。复审 **2026-11-08**。

```bash
# 本机（允许）
bash packages/aiplat-central/scripts/pg_ha_local_rehearsal.sh
bash packages/aiplat-central/scripts/pg_ha_ha_failover_rehearsal.sh

# 有 staging DSN + OIDC 时再开票（无则 blockers，exit 2）
export AIPLAT_PG_DSN='postgresql://…'
export AIPLAT_OIDC_ISSUER='https://…'
bash scripts/ops_pgha_live_kickoff.sh
```

仍 🟨 → 须在 **staging/prod-canary** 完成并写入 live JSON `items`：

| # | checklist | live item key | 做什么 |
|---|-----------|---------------|--------|
| 1 | 租户/OIDC 回归 | `oidc_full` | 租户登录 + admin MFA + API key 路径证据 |
| 2 | PG 迁移演练 | `pg_migration` | 源/目标、行数校验、金丝雀租户 |
| 3 | 备份恢复 | `backup_restore` | 介质、RPO/RTO、恢复验证查询 |
| 4 | HA failover+回切 | `ha_failover` | VIP/流复制、时间线 |
| 7 | 回滚 | `rollback` | 回滚步骤与验证 |

```bash
export AIPLAT_LIVE_DRILL_ID=pgha-live-$(date -u +%Y%m%d)
bash packages/aiplat-central/scripts/pg_ha_record_live_drill.sh
# 编辑 drills/live-$ID.json → items.*.done=true + 非空 evidence
bash scripts/ops_live_sign.sh validate packages/aiplat-central/docs/pg_ha/drills/live-$AIPLAT_LIVE_DRILL_ID.json
bash scripts/ops_live_sign.sh sign     packages/aiplat-central/docs/pg_ha/drills/live-$AIPLAT_LIVE_DRILL_ID.json
# （sign 拒 scaffold env / 未填齐 items；不改 checklist、不 authorize）
# 将 CUTOVER_CHECKLIST 对应 🟨→✅（仅真实完成后）
bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh status
# ready_to_authorize=true 后再：
bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh authorize
```

证据模板：[`LIVE_DRILL_EVIDENCE.md`](../../packages/aiplat-central/docs/pg_ha/LIVE_DRILL_EVIDENCE.md)

## 2) Ontology A3

🟨：#1 healthz 契约 live · #3 存储迁移/双写 · #5 回滚共宿

```bash
export AIPLAT_LIVE_DRILL_ID=ontology-a3-live-$(date -u +%Y%m%d)
bash packages/aiplat-ontology/scripts/a3_record_live_drill.sh
# 填 items → ops_live_sign validate|sign → SPLIT_CHECKLIST ✅
bash scripts/ops_live_sign.sh sign packages/aiplat-ontology/docs/a3/drills/live-$AIPLAT_LIVE_DRILL_ID.json
bash packages/aiplat-ontology/scripts/a3_split_authorize.sh authorize
```

## 3) Evaluation A3

🟨：#1 protocol/healthz live · #4 备份恢复+回滚共宿

```bash
export AIPLAT_LIVE_DRILL_ID=evaluation-a3-live-$(date -u +%Y%m%d)
bash packages/aiplat-evaluation/scripts/a3_record_live_drill.sh
bash scripts/ops_live_sign.sh sign packages/aiplat-evaluation/docs/a3/drills/live-$AIPLAT_LIVE_DRILL_ID.json
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh authorize
```

## 4) Pi D3

🟨：#3 bundle · #4 ops surface · #5 SOC 真实出口 · #6 N-1 升级/回滚

```bash
export AIPLAT_LIVE_DRILL_ID=pi-d3-live-$(date -u +%Y%m%d)
bash packages/aiplat-pi-runtime/scripts/d3_record_live_drill.sh
bash scripts/ops_live_sign.sh sign packages/aiplat-pi-runtime/docs/d3/drills/live-$AIPLAT_LIVE_DRILL_ID.json
bash packages/aiplat-pi-runtime/scripts/d3_authorize.sh authorize
```

## 禁止

- 未真实演练就把 checklist 改 ✅ 或把 `production_signed` 改 true  
- 用 `environment=scaffold` / 本地 docker 🟨 冒充 live  
- 未 `ready_to_authorize=true` 时强跑 `authorize`（脚本会 REFUSE）
