# FDE Field D1 — install（ADR Accepted）

> ADR: [`ADR-FDE-FIELD-DEPLOY.md`](../../../../reports/five-products/ADR-FDE-FIELD-DEPLOY.md) · **Accepted** 2026-10-30

```bash
export AIPLAT_HOME=/tmp/aiplat-fde-d1
export AIPLAT_FDE_PREFIX=$AIPLAT_HOME/fde

bash packages/aiplat-fde/scripts/d1_install.sh --smoke
```

Layout:

```text
$AIPLAT_FDE_PREFIX/
  current -> versions/<ver>
  data/projects/  data/evidence/
  backups/  env  INSTALL_META.json   # production_field=true
```

N-1 / 驻留：[`N1_COMPAT.md`](./N1_COMPAT.md) · [`DATA_RESIDENCY.md`](./DATA_RESIDENCY.md)

签收唯一：`POST /api/platform/apps/fde/acceptance/signoff`  
Compose 长驻：**不含**（另批）。
