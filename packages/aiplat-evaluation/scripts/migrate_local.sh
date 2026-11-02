#!/usr/bin/env bash
# A2: apply standalone eval SQLite migrations (local only).
# Does NOT flip process_split_authorized.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export AIPLAT_EVAL_DB_URL="${AIPLAT_EVAL_DB_URL:-sqlite:///${ROOT}/data/eval_local.sqlite3}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "${ROOT}/data"

python3 - <<'PY'
import json, os
from app.store.migrate import _cli_migrate

url = os.environ["AIPLAT_EVAL_DB_URL"]
out = _cli_migrate(url)
print(json.dumps(out, ensure_ascii=False, indent=2))
assert out["apply"]["ok"] is True
assert out["apply"]["process_split_authorized"] is False
print("A2 migrate_local PASS")
PY
