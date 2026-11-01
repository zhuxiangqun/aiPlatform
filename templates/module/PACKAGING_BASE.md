# Packaging base (V2.1)

Shared D1/D2 file surface for capability packages. Copy stubs from this tree; do not invent a parallel install layout.

## Required D1 Thin

| Script | Role |
|--------|------|
| `scripts/d1_lib.sh` | prefix / version / materialize helpers |
| `scripts/d1_install.sh` | hermetic prefix install |
| `scripts/d1_upgrade.sh` | distinct version slot + `.previous_current` |
| `scripts/d1_rollback.sh` | `--version` / `--backup` / `--runtime` |
| `scripts/d1_smoke.sh` | contract / healthz smoke |
| `scripts/d1_backup.sh` | required for all five packages (Thin tarball) |

## Required D2 pack

| File | Role |
|------|------|
| `security/baseline.yaml` | file-path + snippet checks |
| `scripts/d2_admin_check.sh` | runs shared `scripts/lib/aiplat_security_baseline.py` |
| `scripts/d2_local_closeout.sh` | local evidence; **never** flips authorize hard gates |
| `docs/PERF_BASELINE.md` | local wall-clock budgets（**不是**生产 SLA） |
| `scripts/sbom-sign.stub.sh` | SBOM/sign 命令打印桩（不执行 syft/cosign） |

Central extras: `d2_compat_check.sh` · `d2_security_check.sh` · `docs/D2_THIN.md`.

Perf gate: `bash scripts/check_five_products_perf_baseline.sh`  
Freeze gate: `bash scripts/ops_engineering_freeze_check.sh`

## Hard rules

- `environment=local` evidence ≠ `production_signed`
- `local_signed` ≠ authorize
- Checklist 🟨 must not be hand-flipped to ✅ without live evidence

## Gate

```bash
bash scripts/check_five_products_packaging_surface.sh
```
