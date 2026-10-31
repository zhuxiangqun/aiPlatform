# 四轨暂用本机（Live / Authorize 暂缓）

- decided_at: `2026-10-31`
- decision: 无预发前只跑 local/docker rehearsal；硬门保持 false

| 轨 | 本地状态 | 硬门 |
|----|----------|------|
| PG/HA | prep + docker reh 🟨 | `cutover_authorized=false` |
| Ontology A3 | local reh 🟨 | `process_split_authorized=false` |
| Evaluation A3 | local reh 🟨 | `process_split_authorized=false` |
| Pi D3 | bundle + SOC file-sink 🟨 | `d3_production_authorized=false` |

刷新本机：

```bash
bash packages/aiplat-central/scripts/pg_ha_local_rehearsal.sh
bash packages/aiplat-central/scripts/pg_ha_ha_failover_rehearsal.sh
bash packages/aiplat-ontology/scripts/a3_local_rehearsal.sh
bash packages/aiplat-evaluation/scripts/a3_local_rehearsal.sh
bash packages/aiplat-pi-runtime/scripts/d3_local_rehearsal.sh
bash packages/aiplat-pi-runtime/scripts/d3_soc_local_rehearsal.sh
bash scripts/ops_live_status.sh --json
```

有预发后再按 [`OPS_HANDOFF.md`](../OPS_HANDOFF.md) 做 live → sign → authorize。
