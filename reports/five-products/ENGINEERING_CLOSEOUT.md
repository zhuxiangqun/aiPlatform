# Five-products 工程收口（2026-10-30）

## 工程侧已闭合

| 项 | 状态 |
|----|------|
| 五包 A2 versioning **0.1.0** + `five_products_gate` | ✅ |
| FDE Field D1 | **Accepted** |
| PG/HA ADR | **Accepted（有条件）** + prep/local/docker/HA rehearse + **authorize REFUSE** |
| Ontology / Evaluation A3 | **Accepted（有条件）** + prep/local/prefix + **authorize REFUSE** |
| 本地/docker checklist | 多为 🟨；**不等于**生产授权 |

## 硬门（仍 false）

- `cutover_authorized=false`
- Ontology / Evaluation `process_split_authorized=false`

## 运维 backlog（工程无法代替）

总册：[`OPS_LIVE_RUNBOOK.md`](./OPS_LIVE_RUNBOOK.md) · 只读聚合：`bash scripts/ops_live_status.sh`

1. 按各轨 `LIVE_DRILL_EVIDENCE.md` 填生产类证据 → `*_record_live_drill.sh`  
2. 人工将 checklist 🟨→✅（仅在 live 真实完成后）  
3. `*_authorize.sh authorize`  
4. 再生产切流 / 进程拆分 / D3 宣称  

## 工程增量（收口后）

| 项 | 状态 |
|----|------|
| Pi **D2 admin/security pack** | ✅ `security/baseline.yaml` + `d2_admin_check.sh` + chart enterprise_default=0 |
| Pi **D3 ADR** | ✅ [`ADR-PI-D3`](./ADR-PI-D3.md) **Accepted（有条件）** + prep；本地 bundle+SOC file-sink→🟨；live 模板就绪；`d3_production_authorized=false` |
| **Ops live 总册** | ✅ `OPS_LIVE_RUNBOOK.md` + `scripts/ops_live_status.sh`（只读；不授权） |
| **authorize + signed live** | ✅ 四轨 `*_authorize` 须 checklist 全 ✅ **且** `live-*.json` `production_signed=true`（`scripts/lib/aiplat_live_evidence.py`） |
| **dual-gate regression** | ✅ `scripts/test_live_evidence_authorize_gate.sh`（临时目录；包内硬门仍 false） |
| **Ops handoff + scaffold** | ✅ `OPS_HANDOFF.md` + `ops_live_scaffold.sh`（未签 live；不授权） |
| **ops_live_sign** | ✅ items 齐才可签 `production_signed`；拒 scaffold env；不 authorize |
| **PG/HA live kickoff** | ✅ `ops_pgha_live_kickoff.sh`；缺前置写 `ops/PGHA_LIVE_RUNLOG.md`；不授权 |
| **暂用本机** | ✅ [`ops/LOCAL_DEFER.md`](./ops/LOCAL_DEFER.md) — 四轨 local 🟨；硬门全 false |

## 明确不在本收口

- 五产品对外 E4 / 全拆宣称  
- Pi **D3 生产宣称**（checklist 未全 ✅）  
- compose 长驻 Field  

验证：`bash scripts/five_products_gate.sh`
