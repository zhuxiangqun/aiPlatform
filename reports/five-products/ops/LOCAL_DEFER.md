# 四轨正式 defer（Live / Authorize 暂缓）

- decided_at: `2026-10-31`
- formalized_at: `2026-11-01`
- decision: **路径 B — 正式 defer**（无预发 DSN/OIDC；不假造 staging）
- `staging_ready`: **false**（见 [`STAGING_READY.md`](./STAGING_READY.md)）
- last_kickoff: `2026-10-31T23:35:04Z` · `ops_pgha_live_kickoff.sh` **exit 2**（按设计）
- review_by: **2026-11-08**（若仍无预发则续 defer；有则走路径 A）

| 轨 | 本地状态 | 硬门 |
|----|----------|------|
| PG/HA | prep + docker reh 🟨 | `cutover_authorized=false` |
| Ontology A3 | local reh 🟨 | `process_split_authorized=false` |
| Evaluation A3 | local reh 🟨 | `process_split_authorized=false` |
| Pi D3 | bundle + SOC file-sink 🟨 | `d3_production_authorized=false` |

## 禁止（硬门生效期间）

- 用本地 Docker PG 冒充 `staging`
- 手改 checklist 🟨→✅
- 改 `authorize` 脚本放行
- 把 scaffold live 写成 `production_signed=true`
- 假造 DSN / OIDC

## 并行允许（路径 A · local staging · 非授权）

本机 Docker「local staging」可推进迁移/备份/手动 failover/OIDC 工程验证；证据必须 `environment=local`（`local-*.json`），**不能** authorize。详见 [`LOCAL_STAGING.md`](./LOCAL_STAGING.md)。

```bash
# PG/HA local staging（PG :5433 + Keycloak :8081）
bash packages/aiplat-central/scripts/pg_ha_local_staging.sh all
# 轻量 rehearsal（无 compose）：
bash packages/aiplat-central/scripts/pg_ha_local_rehearsal.sh
bash packages/aiplat-central/scripts/pg_ha_ha_failover_rehearsal.sh
bash packages/aiplat-ontology/scripts/a3_local_rehearsal.sh
bash packages/aiplat-evaluation/scripts/a3_local_rehearsal.sh
bash packages/aiplat-pi-runtime/scripts/d3_local_rehearsal.sh
bash packages/aiplat-pi-runtime/scripts/d3_soc_local_rehearsal.sh
bash scripts/ops_live_status.sh --json
```

## 主轨（defer 期间）

不依赖预发：**Pi D1**（安装器 / healthz / Gate3 回滚面）及其他本地可验工程。  
PG/HA live → sign → authorize 等 `staging_ready=true`。

本地回归（2026-11-01）：[`PI_D1_LOCAL_REGRESSION.md`](./PI_D1_LOCAL_REGRESSION.md) **PASS**

```bash
bash packages/aiplat-pi-runtime/scripts/d1_local_regression.sh
```

## 复审后走路径 A

见 [`PGHA_LIVE_RUNLOG.md`](./PGHA_LIVE_RUNLOG.md) 复审条件 + [`OPS_HANDOFF.md`](../OPS_HANDOFF.md)。
