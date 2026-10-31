# Pi Thin — D1 install / upgrade / rollback

> Scope: **Gate3 Thin only** (ADR-08). No new update channel; no control-plane install.  
> Capability: `pi` · Deploy unit: **edge**

## One-shot install

```bash
# Optional: isolate from real HOME
export AIPLAT_HOME=/tmp/aiplat-pi-d1-demo
export AIPLAT_PI_PREFIX=$AIPLAT_HOME/pi

bash packages/aiplat-pi-runtime/scripts/d1_install.sh --smoke
```

Layout:

```text
$AIPLAT_PI_PREFIX/
  current -> versions/<ver>
  versions/<ver>/     # bin, extensions, skills, contracts, …
  bundles/current ->  # sample-app or --app-home
  env                 # Thin stub defaults (AIPLAT_ENTERPRISE=0)
  bin/aiplat-http
  backups/
```

Start (installed prefix):

```bash
$AIPLAT_PI_PREFIX/bin/aiplat-http
# GET http://127.0.0.1:18787/healthz
# GET http://127.0.0.1:18787/health   # legacy
```

## Upgrade / rollback

```bash
bash packages/aiplat-pi-runtime/scripts/d1_upgrade.sh
# Same package.json version re-upgrade materializes versions/<ver>+<UTC> so runtime rollback can flip.
# Bundle-first (preferred — Gate3):
bash packages/aiplat-pi-runtime/scripts/d1_rollback.sh --bundle /path/to/prev-export
# Runtime:
bash packages/aiplat-pi-runtime/scripts/d1_rollback.sh --runtime
```

Local regression (hermetic; **not** staging authorize):

```bash
bash packages/aiplat-pi-runtime/scripts/d1_local_regression.sh
```

Drill record: [`GATE3_PI_THIN_ROLLBACK_DRILL.md`](../../../reports/five-products/GATE3_PI_THIN_ROLLBACK_DRILL.md) · [`PI_D1_LOCAL_REGRESSION.md`](../../../reports/five-products/ops/PI_D1_LOCAL_REGRESSION.md)

## Backup

```bash
bash packages/aiplat-pi-runtime/scripts/d1_backup.sh
# optional full bundle copy:
AIPLAT_PI_BACKUP_BUNDLE=1 bash packages/aiplat-pi-runtime/scripts/d1_backup.sh
```

## Compose (long-running)

Reuse Gate3:

```bash
docker compose -f packages/aiplat-pi-runtime/compose.gate3-pi-thin.yml up -d
curl -fsS http://127.0.0.1:18787/healthz
```

## ADR note

Installer/packaging for Thin **does not** require ADR-08 revision. Expanding beyond Thin (enterprise update channel, multi-tenant edge) **does**.
