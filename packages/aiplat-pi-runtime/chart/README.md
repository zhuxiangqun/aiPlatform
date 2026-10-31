# Pi chart / deploy notes (D1 + D2 admin)

**Source of truth for long-running Thin:** `compose.gate3-pi-thin.yml` (Gate3 / ADR-08).  
`Chart.yaml` / `values.yaml`：D2 skeleton（`enterprise_default=0`）；复制到集群时勿并行分叉 Thin 路径。

D2 校验：`bash packages/aiplat-pi-runtime/scripts/d2_admin_check.sh`

## Local D1

```bash
bash packages/aiplat-pi-runtime/scripts/d1_install.sh --smoke
curl -fsS http://127.0.0.1:${PORT:-18787}/healthz
```

See [`docs/INSTALL.md`](../docs/INSTALL.md).

## Compose

```bash
docker compose -f packages/aiplat-pi-runtime/compose.gate3-pi-thin.yml up -d
curl -fsS http://127.0.0.1:18787/healthz
```
