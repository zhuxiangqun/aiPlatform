#!/usr/bin/env bash
# Refresh / verify B4-S local rehearsal evidence path (≠ staging).
# Default: docs+script structural gate. Set AIPLAT_EVAL_B4S_RUN=1 to execute rehearsal.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DOC="$ROOT/docs/a3/B4S_LOCAL_REHEARSAL.md"
SCRIPT="$ROOT/scripts/b4s_local_rehearsal.sh"
EVID_DIR="${AIPLAT_EVAL_B4S_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN="${AIPLAT_EVAL_B4S_RUN:-0}"

[[ -f "$DOC" && -f "$SCRIPT" ]] || {
  echo "REFUSE: missing B4S rehearsal doc/script" >&2
  exit 2
}
chmod +x "$SCRIPT" 2>/dev/null || true

ran=false
if [[ "$RUN" == "1" ]]; then
  echo "== execute b4s_local_rehearsal.sh =="
  bash "$SCRIPT"
  ran=true
fi

python3 - <<PY
import json
from pathlib import Path

doc = Path("$DOC").read_text(encoding="utf-8")
assert "environment=local" in doc or "≠ staging" in doc
assert "b4s_local_rehearsal.sh" in doc
script = Path("$SCRIPT").read_text(encoding="utf-8")
assert "not_staging_evidence" in script or "authorize" in script

payload = {
    "schema": "eval.b4s.evidence_refresh.v0",
    "product_id": "evaluation",
    "environment": "local",
    "not_staging_evidence": True,
    "process_split_authorized": False,
    "accuracy_claim": False,
    "rehearsal_executed": "$ran" == "True",
    "doc": "docs/a3/B4S_LOCAL_REHEARSAL.md",
    "script": "scripts/b4s_local_rehearsal.sh",
    "recorded_at": "$STAMP",
    "honesty": "B4-S local path refreshed/verified; not staging host evidence; not authorize",
}
path = Path("$EVID_DIR") / f"local-eval-b4s-evidence-refresh-$STAMP.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"gate": "ok", "evidence": str(path), "rehearsal_executed": payload["rehearsal_executed"]}, ensure_ascii=False))
PY

echo "b4s evidence refresh gate PASS (not_staging_evidence=true; authorize=false)"
