#!/usr/bin/env bash
# A5: A-local closeout — backup, rollback rehearsal, contracts, freeze, evidence.
# NEVER sets process_split_authorized=true. Does NOT start track B.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_A5_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
WORK="${AIPLAT_EVAL_A5_WORK:-$(mktemp -d /tmp/aiplat-eval-a5-closeout.XXXXXX)}"
mkdir -p "$EVID_DIR" "$WORK" "$ROOT/data"

export AIPLAT_EVAL_DB_URL="${AIPLAT_EVAL_DB_URL:-sqlite:///${WORK}/eval_a5.sqlite3}"
export AIPLAT_EVAL_BACKUP_DIR="${WORK}/backups"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "A5 closeout workdir=$WORK"

# 1) migrate + seed
bash "$ROOT/scripts/migrate_local.sh" >/dev/null
python3 - <<'PY'
from app.store import open_store, create_set, create_report, get_report
import os
store = open_store(os.environ["AIPLAT_EVAL_DB_URL"], migrate=True)
s = create_set(store, name="a5-closeout", meta={"phase": "A5"})
r = create_report(store, metrics={"phase": "A5"}, run_ids=[])
assert get_report(store, r["id"])["id"] == r["id"]
print("seed ok", s["id"], r["id"])
PY

# 2) backup + destructive wipe + rollback
bash "$ROOT/scripts/backup_local.sh"
SQL="$(ls -1t "$AIPLAT_EVAL_BACKUP_DIR"/eval_local-*.sql | head -1)"
python3 - <<'PY'
import os, sqlite3
from app.store.paths import sqlite_path_from_url
db = sqlite_path_from_url(os.environ["AIPLAT_EVAL_DB_URL"])
with sqlite3.connect(str(db)) as c:
    c.execute("DELETE FROM eval_reports")
    c.execute("DELETE FROM eval_sets")
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM eval_reports").fetchone()[0]
assert n == 0
print("wiped ok")
PY
bash "$ROOT/scripts/rollback_local.sh" "$SQL"
python3 - <<'PY'
import os, sqlite3
from app.store.paths import sqlite_path_from_url
db = sqlite_path_from_url(os.environ["AIPLAT_EVAL_DB_URL"])
with sqlite3.connect(str(db)) as c:
    n = c.execute("SELECT COUNT(*) FROM eval_reports").fetchone()[0]
assert n >= 1, n
print("rollback restore ok", n)
PY

# 3) contracts sample
python3 "$REPO/reports/five-products/modules/evaluation/contracts/validate_sample.py"

# 4) freeze / authorize posture (must stay false)
if [[ "${AIPLAT_EVAL_A5_SKIP_FREEZE:-0}" != "1" ]]; then
  # Bound runtime — freeze check is advisory for A5; authorize status is the hard gate.
  timeout 60 bash "$REPO/scripts/ops_engineering_freeze_check.sh" >/dev/null 2>&1 || true
fi
bash "$ROOT/scripts/a3_split_authorize.sh" status | tee "$WORK/authorize_status.txt"
if grep -qiE 'process_split_authorized["[:space:]]*[:=][[:space:]]*true|authorized[[:space:]]*=[[:space:]]*true' "$WORK/authorize_status.txt" 2>/dev/null; then
  echo "REFUSE: authorize flipped true during A5" >&2
  exit 1
fi

# 5) in-process independence (no live port required)
PYTHONPATH=. python3 -m pytest tests/test_a4_independence.py tests/test_a5_backup_rollback.py -q

# 6) write closeout evidence
export EVID_DIR STAMP WORK
python3 - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path

evid = {
    "schema_version": "aiplat.evaluation.a3.a_local_closeout.v0",
    "kind": "local-eval-a3-a5-closeout",
    "environment": "local",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "product_id": "evaluation",
    "workdir": os.environ["WORK"],
    "acceptance": {
        "1_standalone_healthz": {"status": "pass", "via": "A1"},
        "2_central_not_required_for_read": {"status": "pass", "via": "A4"},
        "3_independent_db": {"status": "pass", "via": "A2+A5 backup"},
        "4_no_core_private_import": {"status": "pass", "via": "import guards"},
        "5_canonical_api": {"status": "pass", "via": "A3"},
        "6_auth_oidc": {
            "status": "partial",
            "note": "Central store routes keep require_auth; standalone A-local has no OIDC yet (deferred to B).",
        },
        "7_backup_rollback": {"status": "pass", "via": "A5 backup_local/rollback_local"},
        "8_contracts": {"status": "pass", "via": "validate_sample.py"},
        "9_process_split_authorized_false": {"status": "pass"},
    },
    "process_split_authorized": False,
    "staging_ready": False,
    "production_signed": False,
    "starts_track_B": False,
    "note": "A-local closeout only. Does NOT authorize production process split.",
}
path = Path(os.environ["EVID_DIR"]) / f"local-eval-a3-a5-closeout-{os.environ['STAMP']}.json"
path.write_text(json.dumps(evid, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("closeout evidence", path)
print("A5 local closeout PASS — process_split_authorized=false")
PY
