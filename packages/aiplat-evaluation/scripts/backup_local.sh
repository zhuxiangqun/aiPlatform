#!/usr/bin/env bash
# A5: backup standalone eval SQLite (local only). process_split stays false.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DB_URL="${AIPLAT_EVAL_DB_URL:-sqlite:///${ROOT}/data/eval_local.sqlite3}"
BACKUP_DIR="${AIPLAT_EVAL_BACKUP_DIR:-${ROOT}/data/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export AIPLAT_EVAL_DB_URL="$DB_URL"
export AIPLAT_EVAL_BACKUP_DIR="$BACKUP_DIR"
export AIPLAT_EVAL_BACKUP_STAMP="$STAMP"

python3 - <<'PY'
import os, shutil, sqlite3
from pathlib import Path
from app.store.paths import sqlite_path_from_url

db = sqlite_path_from_url(os.environ["AIPLAT_EVAL_DB_URL"])
if not db.is_file():
    raise SystemExit(f"missing db: {db}")
out_dir = Path(os.environ["AIPLAT_EVAL_BACKUP_DIR"])
stamp = os.environ["AIPLAT_EVAL_BACKUP_STAMP"]
# online-safe: dump SQL + copy file
sql_path = out_dir / f"eval_local-{stamp}.sql"
bin_path = out_dir / f"eval_local-{stamp}.sqlite3"
with sqlite3.connect(str(db)) as conn, sql_path.open("w", encoding="utf-8") as f:
    for line in conn.iterdump():
        f.write(line + "\n")
shutil.copy2(db, bin_path)
import json
meta = out_dir / f"eval_local-{stamp}.meta.json"
meta.write_text(
    json.dumps(
        {
            "ok": True,
            "db": str(db),
            "sql": str(sql_path),
            "sqlite_copy": str(bin_path),
            "process_split_authorized": False,
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print("OK backup sql", sql_path)
print("OK backup sqlite", bin_path)
print("process_split_authorized=false")
PY
