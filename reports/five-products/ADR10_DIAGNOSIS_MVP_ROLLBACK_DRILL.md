# ADR-10 诊断 MVP — Rollback（Phase A）

| Field | Value |
|-------|-------|
| Scene | `fp-customer-lock-service-bundle-pi-diag-001` |
| Date | 2026-10-24 |
| Result | **PASS**（smoke + refuse + rm home） |
| Residual | 夹具 JSONL；无容器长驻；无 7×24 |

```bash
bash scripts/adr10_diagnosis_mvp_pilot.sh
AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 bash scripts/adr10_diagnosis_mvp_pilot.sh  # exit 3
rm -rf /tmp/aiplat-adr10-diag-home
```
