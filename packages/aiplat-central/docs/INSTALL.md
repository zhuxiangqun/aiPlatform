# aiPlat Central — D1 Thin install / upgrade / rollback

> Scope: **Central host packaging only**. No PG/HA multi-process split (needs ADR).  
> Capability: `aiplat` · Deploy unit: **central**

## One-shot install + smoke

```bash
# Optional: isolate from real HOME
export AIPLAT_HOME=/tmp/aiplat-central-d1-demo
export AIPLAT_CENTRAL_PREFIX=$AIPLAT_HOME/central

bash packages/aiplat-central/scripts/d1_install.sh --smoke
```

Layout:

```text
$AIPLAT_CENTRAL_PREFIX/
  current -> versions/<ver>
  versions/<ver>/     # scripts, contracts, REPO_ROOT pointers
  env                 # AIPLAT_CORE_HOST/PORT
  bin/aiplat-core-healthz
  backups/
  INSTALL_META.json
```

Probe a running core (after `scripts/dev.sh core` or equivalent):

```bash
$AIPLAT_CENTRAL_PREFIX/bin/aiplat-core-healthz
# → GET /api/core/healthz  product_id=aiplat
```

## Smoke without long-running server

`d1_smoke.sh` boots an in-process FastAPI TestClient against `core.server.app` with an isolated `HOME`, asserts A1 healthz + `control_plane.v0`.

```bash
bash packages/aiplat-central/scripts/d1_smoke.sh
```

## Upgrade / rollback / backup

```bash
bash packages/aiplat-central/scripts/d1_upgrade.sh
bash packages/aiplat-central/scripts/d1_backup.sh
bash packages/aiplat-central/scripts/d1_rollback.sh --version 0.1.0
# or:
bash packages/aiplat-central/scripts/d1_rollback.sh --backup $AIPLAT_CENTRAL_PREFIX/backups/….tgz
```

## Non-goals (this Thin)

- Postgres / HA topology  
- Shipping vendored wheels of core/platform (uses monorepo pointers)  
- Field / Edge deploy units  
