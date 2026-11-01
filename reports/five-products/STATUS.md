# Five-products engineering status (2026-11-01)

> **SSOT autonomy/delivery**：[`capabilities.manifest.yaml`](../../capabilities.manifest.yaml)（本表必须与之一致；禁止写高于 manifest 的 A/D）。  
> **G0**：[`G0_CLOSEOUT.md`](./G0_CLOSEOUT.md)（通过 · P0-3′ · 19 提交 · CI 证据）。  
> 工程收口见 [`ENGINEERING_CLOSEOUT.md`](./ENGINEERING_CLOSEOUT.md) · 本地收口 [`ops/ENGINEERING_LOCAL_CLOSEOUT.md`](./ops/ENGINEERING_LOCAL_CLOSEOUT.md)。  
> **运维决策（2026-11-01）**：**运维路径 B — 正式 defer**；`staging_ready=false`（[`ops/STAGING_READY.md`](./ops/STAGING_READY.md)）。复审：**2026-11-08**。  
> **工程环境**：**方案 B 本机 VM/Docker 全轨**（[`ops/OPTION_B_LOCAL_VM.md`](./ops/OPTION_B_LOCAL_VM.md)）· `bash scripts/ops_option_b_all.sh`。  
> Blocker：缺**真实**预发 DSN/OIDC（本机 local ≠ staging）；kickoff exit 2 = 硬门按设计。  
> **Accepted（有条件）** ≠ 生产授权；硬门全 **false**。

| Capability | Autonomy | Delivery | Mode | Package | Healthz | ADR / notes |
|------------|----------|----------|------|---------|---------|-------------|
| **aiplat** | **A0** | **D2** (+ Thin local) | standalone (thin) | `aiplat-central` + platform | `/api/core/healthz` | PG/HA Accepted（有条件）；`cutover=false`；[D2 Thin](../../packages/aiplat-central/docs/D2_THIN.md) |
| **pi** | **A3** (Thin) | **D1** (+ D2 admin / D3 prep) | edge | `aiplat-pi-runtime` **0.1.0** | `/healthz` | ADR-08 · [D3 Accepted（有条件）](./ADR-PI-D3.md)；`d3_production=false` |
| **ontology** | **A2** | **D1** (D1c + D2 pack) | **cohost** | `aiplat-ontology` **0.1.0** | `/ontology/healthz` | [A3 Accepted（有条件）](./ADR-ONTOLOGY-A3.md)；`process_split=false` |
| **evaluation** | **A2** | **D1** (D1c + D2 pack) | **cohost** | `aiplat-evaluation` **0.1.0** | `/eval/healthz` | [A3 Accepted（有条件）](./ADR-EVALUATION-A3.md)；`process_split=false` |
| **fde** | **A1** | **D1** Field (+ D2 ops) | field | `aiplat-fde` **0.1.0** | `/fde/healthz` | [Field Accepted](./ADR-FDE-FIELD-DEPLOY.md)；D2 pack 见下 |

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
| Pi D3 local closeout | [`ops/PI_D3_LOCAL_CLOSEOUT.md`](./ops/PI_D3_LOCAL_CLOSEOUT.md) **PASS**（#3–#6 🟨；authorize REFUSE） |
| 四轨 local_signed | [`ops/LOCAL_TRACKS_RUNLOG.md`](./ops/LOCAL_TRACKS_RUNLOG.md) |
| FDE Field install/meta | [`ops/FDE_FIELD_LOCAL_REGRESSION.md`](./ops/FDE_FIELD_LOCAL_REGRESSION.md) **PASS** |
| FDE Field D2 ops pack | [`ops/FDE_FIELD_D2_LOCAL_CLOSEOUT.md`](./ops/FDE_FIELD_D2_LOCAL_CLOSEOUT.md) **PASS** |
| Ontology D2 cohost pack | [`ops/ONTOLOGY_D2_LOCAL_CLOSEOUT.md`](./ops/ONTOLOGY_D2_LOCAL_CLOSEOUT.md) **PASS** |
| Evaluation D2 cohost pack | [`ops/EVALUATION_D2_LOCAL_CLOSEOUT.md`](./ops/EVALUATION_D2_LOCAL_CLOSEOUT.md) **PASS** |
| aiPlat Central D2 Thin | [`ops/AIPLAT_D2_THIN_LOCAL_CLOSEOUT.md`](./ops/AIPLAT_D2_THIN_LOCAL_CLOSEOUT.md) **PASS**（cutover REFUSE） |
| Local staging 总册 | [`ops/LOCAL_STAGING.md`](./ops/LOCAL_STAGING.md) · 方案 B [`ops/OPTION_B_LOCAL_VM.md`](./ops/OPTION_B_LOCAL_VM.md) |
| Option B 最近全跑 | [`ops/OPTION_B_LAST_RUN.md`](./ops/OPTION_B_LAST_RUN.md) **PASS** |
| STATUS↔manifest | `python3 scripts/check_five_products_status_sync.py` |
