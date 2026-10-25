# ADR-10 诊断 MVP — Rollback（Phase A–B）

| Field | Value |
|-------|-------|
| Scene | `fp-customer-lock-service-bundle-pi-diag-001` |
| Date | 2026-10-24 |
| Result | **PASS**（宿主 smoke + refuse；compose 文件已交付） |
| Residual | compose 需联网 `pip install` 最小依赖；无生产默认切换；无 7×24 |

## Priority

1. 停 compose / 清 volume：`docker compose -f compose.adr10-diagnosis-mvp.yml down -v`  
2. 清宿主沙箱：`rm -rf /tmp/aiplat-adr10-diag-home`  
3. 禁用以本演练证明「已切生产默认」

```bash
bash scripts/adr10_diagnosis_mvp_pilot.sh
AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 bash scripts/adr10_diagnosis_mvp_pilot.sh  # exit 3
docker compose -f compose.adr10-diagnosis-mvp.yml run --rm adr10-diagnosis-mvp
docker compose -f compose.adr10-diagnosis-mvp.yml down -v
```
