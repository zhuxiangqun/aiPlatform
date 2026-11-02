#!/usr/bin/env bash
# A5: restore eval SQLite from a backup and clear proxy URL (back to cohost posture).
# Does NOT delete source backups. process_split stays false.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${AIPLAT_EVAL_BACKUP_DIR:-${ROOT}/data/backups}"
DB_URL="${AIPLAT_EVAL_DB_URL:-sqlite:///${ROOT}/data/eval_local.sqlite3}"
TARGET="${1:-}"

if [[ -z "$TARGET" ]]; then
  # latest .sql in backup dir
  TARGET="$(ls -1t "$BACKUP_DIR"/eval_local-*.sql 2>/dev/null | head -1 || true)"
fi
if [[ -z "$TARGET" || ! -f "$TARGET" ]]; then
  echo "usage: $0 <backup.sql|backup.sqlite3>" >&2
  echo "or place backups under $BACKUP_DIR" >&2
  exit 2
fi

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export AIPLAT_EVAL_DB_URL="$DB_URL"
export AIPLAT_EVAL_ROLLBACK_SRC="$TARGET"

python3 - <<'PY'
import os, shutil, sqlite3
from pathlib import Path
from app.store.paths import sqlite_path_from_url
from app.store.migrate import apply_migrations

src = Path(os.environ["AIPLAT_EVAL_ROLLBACK_SRC"])
db = sqlite_path_from_url(os.environ["AIPLAT_EVAL_DB_URL"])
db.parent.mkdir(parents=True, exist_ok=True)
# keep previous as .pre-rollback
if db.is_file():
    pre = db.with_suffix(db.suffix + ".pre-rollback")
    shutil.copy2(db, pre)
    print("saved pre-rollback", pre)

if src.suffix == ".sql":
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(src.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
elif src.suffix in {".sqlite3", ".db", ".sqlite"}:
    shutil.copy2(src, db)
else:
    raise SystemExit(f"unsupported backup type: {src}")

# ensure migrations table / schema version stamped
apply_migrations(db)
print("OK restored", db, "from", src)
print("hint: unset AIPLAT_EVAL_SERVICE_URL to return Central to cohost")
print("process_split_authorized=false")
PY

# Clear proxy env in this shell session note (caller must export unset)
if [[ -n "${AIPLAT_EVAL_SERVICE_URL:-}" ]]; then
  echo "NOTE: AIPLAT_EVAL_SERVICE_URL is set (${AIPLAT_EVAL_SERVICE_URL}). Unset it for cohost:"
  echo "  unset AIPLAT_EVAL_SERVICE_URL"
fi
