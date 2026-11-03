#!/usr/bin/env bash
# B3-L.2 dual-read local drill — fixture ETL + reconcile + rollback pointer.
# NEVER sets process_split_authorized=true. NO production data.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_B3L_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
WORK="${AIPLAT_EVAL_B3L_WORK:-$(mktemp -d /tmp/aiplat-eval-b3l-dual.XXXXXX)}"
mkdir -p "$EVID_DIR" "$WORK"

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export AIPLAT_EVAL_B3L_SRC="sqlite:///${WORK}/cohost_fixture.sqlite3"
export AIPLAT_EVAL_B3L_DST="sqlite:///${WORK}/eval_target.sqlite3"
export AIPLAT_EVAL_B3L_POINTER="${WORK}/read_pointer.json"
export AIPLAT_EVAL_B3L_EVID_DIR="$EVID_DIR"
export AIPLAT_EVAL_B3L_STAMP="$STAMP"
export AIPLAT_EVAL_B3L_WORKDIR="$WORK"

echo "B3-L dual-read workdir=$WORK"

python3 - <<'PY'
import json
import os
from pathlib import Path

from app.migrate.dual_read import (
    etl_copy_sets_reports,
    inventory_store,
    read_read_pointer,
    reconcile_inventories,
    write_read_pointer,
)
from app.store import open_store
from app.store.store import create_report, create_set

src_url = os.environ["AIPLAT_EVAL_B3L_SRC"]
dst_url = os.environ["AIPLAT_EVAL_B3L_DST"]
pointer = Path(os.environ["AIPLAT_EVAL_B3L_POINTER"])
evid_dir = Path(os.environ["AIPLAT_EVAL_B3L_EVID_DIR"])
stamp = os.environ["AIPLAT_EVAL_B3L_STAMP"]
workdir = os.environ["AIPLAT_EVAL_B3L_WORKDIR"]

src = open_store(src_url, migrate=True)
create_set(
    src,
    name="b3l-set-a",
    meta={"phase": "B3-L"},
    set_id="set_b3l_a",
    tenant_id="tenant-a",
)
create_set(
    src,
    name="b3l-set-b",
    meta={"phase": "B3-L"},
    set_id="set_b3l_b",
    tenant_id="tenant-a",
)
create_report(
    src,
    report_id="rpt_b3l_1",
    metrics={"score": 0.9, "phase": "B3-L"},
    run_ids=["run_1"],
    tenant_id="tenant-a",
)
create_report(
    src,
    report_id="rpt_b3l_2",
    metrics={"score": 0.5, "phase": "B3-L"},
    run_ids=[],
    tenant_id="tenant-a",
)

dst = open_store(dst_url, migrate=True)
etl = etl_copy_sets_reports(src, dst, tenant_id="tenant-a")
assert etl["copied_sets"] == 2 and etl["copied_reports"] == 2, etl

inv_s = inventory_store(src, tenant_id="tenant-a", label="cohost")
inv_t = inventory_store(dst, tenant_id="tenant-a", label="eval")
rec = reconcile_inventories(inv_s, inv_t)
assert rec["ok"] is True, rec

write_read_pointer(pointer, mode="eval", reason="dual_read_ok")
assert read_read_pointer(pointer)["mode"] == "eval"
rb = write_read_pointer(pointer, mode="cohost", reason="drill_rollback")
assert rb["mode"] == "cohost"
assert rb["process_split_authorized"] is False

create_report(
    dst,
    report_id="rpt_extra",
    metrics={"score": 0.0},
    tenant_id="tenant-a",
)
inv_t2 = inventory_store(dst, tenant_id="tenant-a", label="eval_dirty")
rec_bad = reconcile_inventories(inv_s, inv_t2)
assert rec_bad["ok"] is False
assert "rpt_extra" in rec_bad["extra_reports"]

out = {
    "schema": "eval.b3l.dual_read_drill.v0",
    "product_id": "evaluation",
    "phase": "B3-L.2",
    "environment": "local",
    "process_split_authorized": False,
    "staging_ready": False,
    "recorded_at": stamp,
    "workdir": workdir,
    "etl": etl,
    "reconcile_ok": rec,
    "reconcile_dirty": {
        "ok": rec_bad["ok"],
        "extra_reports": rec_bad["extra_reports"],
    },
    "rollback_pointer": rb,
    "honesty": "local fixture dual-read only — not production backfill / authorize",
}
path = evid_dir / f"local-eval-b3l-dual-read-{stamp}.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"drill": "ok", "evidence": str(path), "reconcile_ok": True}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status | tee "$WORK/authorize_status.txt" >/dev/null
if grep -qiE 'process_split_authorized["[:space:]]*[:=][[:space:]]*true|authorized[[:space:]]*=[[:space:]]*true' "$WORK/authorize_status.txt" 2>/dev/null; then
  echo "REFUSE: authorize flipped true during B3-L dual-read" >&2
  exit 1
fi

echo "B3-L dual-read drill PASS (process_split_authorized=false)"
