# Five-products engineering status (2026-11-01)

> **SSOT autonomy/delivery**：[`capabilities.manifest.yaml`](../../capabilities.manifest.yaml)（本表必须与之一致）。  
> 工程收口见 [`ENGINEERING_CLOSEOUT.md`](./ENGINEERING_CLOSEOUT.md)。  
> **运维决策（2026-11-01）**：**路径 B — 正式 defer** PG/HA（及依赖预发的 live）；`staging_ready=false`（[`ops/STAGING_READY.md`](./ops/STAGING_READY.md)）。  
> Blocker：缺预发 `AIPLAT_PG_DSN` + `AIPLAT_OIDC_ISSUER`（kickoff exit 2 = 硬门按设计）。复审：**2026-11-08**。  
> 主轨暂转 **Pi D1**（不依赖预发）；本地 rehearsal 仅路径 C（`local`，不 authorize）。  
> **Accepted（有条件）** = 聊天联签通过路径 + 硬门仍 false；**≠** 生产切流/拆分/D3 就绪。

| Capability | Autonomy | Delivery | Package | Healthz | ADR |
|------------|----------|----------|---------|---------|-----|
| **aiplat** | **A0** | D2 thin | `aiplat-central` **0.1.0** | `/api/core/healthz` | PG/HA **Accepted（有条件）** |
| **pi** | Thin | **D1** · D2 admin · D3 prep | `aiplat-pi-runtime` **0.1.0** | Pi `/healthz` | ADR-08 · [D3 Accepted（有条件）](./ADR-PI-D3.md) |
| **ontology** | A2 | D1 co-host | `aiplat-ontology` **0.1.0** | `/ontology/healthz` | [A3 Accepted（有条件）](./ADR-ONTOLOGY-A3.md) |
| **evaluation** | A2 | D1 co-host | `aiplat-evaluation` **0.1.0** | `/eval/healthz` | [A3 Accepted（有条件）](./ADR-EVALUATION-A3.md) |
| **fde** | A2 | **Field D1** | `aiplat-fde` **0.1.0** | `/fde/healthz` | **Field Accepted** |

## Gate

```bash
bash scripts/five_products_gate.sh
```

## 联签（路径批准 · 非生产授权）

1. Field D1 Accepted  
2. PG/HA Accepted（有条件）  
3. Ontology A3 Accepted（有条件）  
4. Evaluation A3 Accepted（有条件）  
5. [`ADR-PI-D3.md`](./ADR-PI-D3.md) — Pi D3 Accepted（有条件）  

## 硬门（全部 false，直至 checklist 全 ✅ + signed live）

| 门 | 值 |
|----|-----|
| `cutover_authorized` | **false** |
| Ontology / Eval `process_split_authorized` | **false** |
| Pi `d3_production_authorized` | **false**（本地多为 🟨；SOC live 仍须） |

**正式 defer**（[`ops/LOCAL_DEFER.md`](./ops/LOCAL_DEFER.md) · [`ops/PGHA_LIVE_RUNLOG.md`](./ops/PGHA_LIVE_RUNLOG.md)）：四轨 checklist 仍 🟨；切流/拆分/D3 硬门全 **false**；未改 authorize / 未假造 DSN。

运维入口：[`OPS_LIVE_RUNBOOK.md`](./OPS_LIVE_RUNBOOK.md) · [`OPS_HANDOFF.md`](./OPS_HANDOFF.md) · [`ops/STAGING_READY.md`](./ops/STAGING_READY.md) · `bash scripts/ops_live_status.sh`

`staging_ready=true` 后再按交接卡 live → sign → authorize；此前工程主轨走 Pi D1。

Pi D1 本地回归（2026-11-01）：[`ops/PI_D1_LOCAL_REGRESSION.md`](./ops/PI_D1_LOCAL_REGRESSION.md) **PASS**（`d1_local_regression.sh`；environment=local，未授权）。
