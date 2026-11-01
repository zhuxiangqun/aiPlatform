# Diagnosis — D1 Thin install (cohost)

```bash
export AIPLAT_HOME="${AIPLAT_HOME:-$HOME/.aiplat}"
bash packages/aiplat-diagnosis/scripts/d1_install.sh
# optional: bash packages/aiplat-diagnosis/scripts/d1_install.sh --smoke
bash packages/aiplat-diagnosis/scripts/d1_upgrade.sh
bash packages/aiplat-diagnosis/scripts/d1_rollback.sh --runtime
bash packages/aiplat-diagnosis/scripts/d1_backup.sh
```

Prefix: `$AIPLAT_HOME/diagnosis`（或 `AIPLAT_DIAGNOSIS_PREFIX`）。  
`process_split_authorized=false`；独立进程部署需 ADR + live checklist。
