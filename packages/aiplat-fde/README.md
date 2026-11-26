# aiplat-fde

FDE **Field D1** packaging · ADR **Accepted** (`ADR-FDE-FIELD-DEPLOY`) · **Field D2 ops pack**.

- Install/upgrade/backup/rollback/smoke: `scripts/d1_*.sh`
- D2 pack: [`docs/D2_FIELD.md`](./docs/D2_FIELD.md) · `scripts/d2_admin_check.sh` · `scripts/d2_local_closeout.sh`
- Docs: [`docs/INSTALL.md`](./docs/INSTALL.md) · N-1 · data residency
- Healthz: `GET /api/core/fde/healthz` (`production_field=true`)
- Signoff: `POST /api/platform/apps/fde/acceptance/signoff`

## 可选 compose 长驻（F11）

授权：`ADR-FDE-COMPOSE-LONG-RUNNING`（Accepted）。**正式可选**；≠ 强制生产默认；≠ Field 卷包 Draft。

```bash
docker compose -f compose.fde-long-running.yml up -d
curl -fsS http://127.0.0.1:18766/health
docker compose -f compose.fde-long-running.yml down -v
# 烟测
bash ../../scripts/adr09_compose_fde_long_running_smoke.sh
```

基线服务：`compose.fde-optional-health.yml`（长驻文件 `include` + `restart: unless-stopped`）。
