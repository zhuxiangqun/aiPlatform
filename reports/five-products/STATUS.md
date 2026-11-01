# Five-products engineering status (2026-11-01)

> **SSOT autonomy/delivery**：[`capabilities.manifest.yaml`](../../capabilities.manifest.yaml)（本表必须与之一致；禁止写高于 manifest 的 A/D）。  
> 工程收口见 [`ENGINEERING_CLOSEOUT.md`](./ENGINEERING_CLOSEOUT.md) · 本地收口 [`ops/ENGINEERING_LOCAL_CLOSEOUT.md`](./ops/ENGINEERING_LOCAL_CLOSEOUT.md)。  
> **运维决策（2026-11-01）**：**路径 B — 正式 defer**；`staging_ready=false`（[`ops/STAGING_READY.md`](./ops/STAGING_READY.md)）。复审：**2026-11-08**。  
> Blocker：缺预发 `AIPLAT_PG_DSN` + `AIPLAT_OIDC_ISSUER`（kickoff exit 2 = 硬门按设计）。  
> **Accepted（有条件）** ≠ 生产授权；硬门全 **false**。

| Capability | Autonomy | Delivery | Mode | Package | Healthz | ADR / notes |
|------------|----------|----------|------|---------|---------|-------------|
| **aiplat** | **A0** | **D2** | standalone (thin) | `aiplat-central` + platform | `/api/core/healthz` | PG/HA Accepted（有条件）；`cutover=false` |
| **pi** | **A3** (Thin) | **D1** (+ D2 admin / D3 prep) | edge | `aiplat-pi-runtime` **0.1.0** | `/healthz` | ADR-08 · [D3 Accepted（有条件）](./ADR-PI-D3.md)；`d3_production=false` |
| **ontology** | **A2** | **D1** (D1c) | **cohost** | `aiplat-ontology` **0.1.0** | `/ontology/healthz` | [A3 Accepted（有条件）](./ADR-ONTOLOGY-A3.md)；`process_split=false` |
| **evaluation** | **A2** | **D1** (D1c) | **cohost** | `aiplat-evaluation` **0.1.0** | `/eval/healthz` | [A3 Accepted（有条件）](./ADR-EVALUATION-A3.md)；`process_split=false` |
| **fde** | **A1** | **D1** Field | field | `aiplat-fde` **0.1.0** | `/fde/healthz` | [Field Accepted](./ADR-FDE-FIELD-DEPLOY.md)；local install drill 见下 |

**Delivery 语义**：**D1c** = `delivery_mode: cohost`（契约/healthz 独立，**进程仍共宿中心**；≠ 独立部署）。独立拆分仍受 A3 `process_split_authorized=false` 约束。

## Gate

```bash
bash scripts/five_products_gate.sh
```

## 联签（路径批准 · 非生产授权）

1. Field D1 Accepted  
2. PG/HA Accepted（有条件）  
3. Ontology A3 Accepted（有条件）  
4. Evaluation A3 Accepted（有条件）  
5. Pi D3 Accepted（有条件）  

## 硬门（全部 false）

| 门 | 值 |
|----|-----|
| `cutover_authorized` | **false** |
| Ontology / Eval `process_split_authorized` | **false** |
| Pi `d3_production_authorized` | **false** |

**正式 defer**：[`ops/LOCAL_DEFER.md`](./ops/LOCAL_DEFER.md) · [`ops/PGHA_LIVE_RUNLOG.md`](./ops/PGHA_LIVE_RUNLOG.md)

运维：[`OPS_LIVE_RUNBOOK.md`](./OPS_LIVE_RUNBOOK.md) · [`OPS_HANDOFF.md`](./OPS_HANDOFF.md) · [`ops/STAGING_READY.md`](./ops/STAGING_READY.md) · `bash scripts/ops_live_status.sh`

## 本地证据（非生产）

| 项 | 状态 |
|----|------|
| Pi D1 hermetic | [`ops/PI_D1_LOCAL_REGRESSION.md`](./ops/PI_D1_LOCAL_REGRESSION.md) **PASS** |
| Pi D2 admin pack | [`ops/PI_D2_ADMIN_LOCAL.md`](./ops/PI_D2_ADMIN_LOCAL.md) **PASS**（enterprise 默认 off） |
| 四轨 local_signed | [`ops/LOCAL_TRACKS_RUNLOG.md`](./ops/LOCAL_TRACKS_RUNLOG.md) |
| FDE Field install/meta | [`ops/FDE_FIELD_LOCAL_REGRESSION.md`](./ops/FDE_FIELD_LOCAL_REGRESSION.md) **PASS** |
| Local staging 总册 | [`ops/LOCAL_STAGING.md`](./ops/LOCAL_STAGING.md) |
| STATUS↔manifest | `python3 scripts/check_five_products_status_sync.py` |
