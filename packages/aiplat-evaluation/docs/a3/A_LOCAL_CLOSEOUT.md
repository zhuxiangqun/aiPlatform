# EVAL A3 A-local closeout

> **status**: closeout evidence via `bash scripts/a5_local_closeout.sh`  
> **Honesty**: `process_split_authorized=false` · `staging_ready=false` · does **not** start track B  
> Plan: [`eval-a3-independent-service.md`](../../../../docs/architecture/plans/eval-a3-independent-service.md)

## Acceptance (A-local 9)

| # | Item | Result | Evidence |
|---|------|:------:|----------|
| 1 | Independent start `:8010` | ✅ | A1 `run_local.sh` / healthz |
| 2 | Central not required for read | ✅ | A4 `independence_check.sh` |
| 3 | Independent DB | ✅ | A2 migrations + A5 backup |
| 4 | No core private imports | ✅ | package import-guard tests |
| 5 | Canonical store API | ✅ | A3 standalone + optional Central proxy |
| 6 | OIDC / tenant 401–404 | ✅ | A6 local HS256 JWT (`AIPLAT_EVAL_REQUIRE_AUTH`); no token → 401; cross-tenant → 404; Keycloak JWKS still B |
| 7 | Backup / rollback | ✅ | `backup_local.sh` / `rollback_local.sh` |
| 8 | Contracts | ✅ | `validate_sample.py` in closeout |
| 9 | `process_split_authorized` false | ✅ | healthz / authorize status / closeout JSON |

## Commands

```bash
bash packages/aiplat-evaluation/scripts/a5_local_closeout.sh
bash packages/aiplat-evaluation/scripts/backup_local.sh
bash packages/aiplat-evaluation/scripts/rollback_local.sh   # latest or path arg
```

## Exit

- A-local **engineering proof complete** (incl. #6 local JWT).
- **Not** production split. Track B needs staging + real OIDC/JWKS + checklist ✅ + signed live.
