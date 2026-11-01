# Explicit unfreeze — D3 local acceptance + cross-capability E2E

- decided_at: `2026-11-01`
- decision: **解冻**下列两项（本地工程）
- **仍冻结**：任何 `staging_ready` / `production_signed` / `*_authorize` 成功路径

## Unfrozen

| 项 | 入口 |
|----|------|
| D3 本地验收 harness | `bash scripts/ops_d3_local_acceptance_all.sh` |
| 跨能力 E2E（local） | `bash scripts/ops_five_products_e2e_local.sh` |

## Still frozen

- PG/HA cutover authorize  
- Ontology / Evaluation process_split authorize  
- Pi d3_production authorize  
- 手改 checklist 🟨→✅  
- 本机 Docker 冒充 staging  

见 [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)。
