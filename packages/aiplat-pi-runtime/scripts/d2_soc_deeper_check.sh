#!/usr/bin/env bash
# Pi D2++ SOC deeper check — validates latest local soc-rehearsal JSON shape.
# environment=local only. Never production_signed / authorize.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
DRILL="$ROOT/packages/aiplat-pi-runtime/docs/d3/drills"
fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

[[ -d "$DRILL" ]] || fail "missing $DRILL"
LATEST="$(ls -1t "$DRILL"/soc-rehearsal-*.json 2>/dev/null | head -1 || true)"
if [[ -z "$LATEST" ]]; then
  echo "WARN: no soc-rehearsal yet — running local SOC rehearsal"
  bash "$SCRIPT_DIR/d3_soc_local_rehearsal.sh" || fail "d3_soc_local_rehearsal"
  LATEST="$(ls -1t "$DRILL"/soc-rehearsal-*.json 2>/dev/null | head -1 || true)"
fi
[[ -n "$LATEST" ]] || fail "still no soc-rehearsal json"

export AIPLAT_SOC_JSON="$LATEST"
python3 - <<'PY'
import json, os, sys
from pathlib import Path
p = Path(os.environ["AIPLAT_SOC_JSON"])
data = json.loads(p.read_text(encoding="utf-8"))
errors = []
# Accept common local rehearsal shapes without inventing production claims
env = str(data.get("environment") or data.get("env") or "")
if env and env not in ("local", "file-sink", "rehearsal"):
    if env in ("staging", "prod", "production"):
        errors.append(f"environment={env!r} not allowed for local D2++ check")
for key in ("kind", "at", "stamp", "recorded_at", "ts"):
    if key in data:
        break
else:
    # allow nested evidence
    if not any(k in data for k in ("events", "sink", "path", "file")):
        errors.append("missing timestamp-ish or sink field")
text = p.read_text(encoding="utf-8")
if "production_signed\": true" in text or '"production_signed": true' in text:
    errors.append("production_signed must not be true in local soc rehearsal")
if errors:
    print("FAIL d2_soc_deeper_check:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print(f"OK d2_soc_deeper_check file={p} environment={env or 'unspecified-local'}")
PY
pass "Pi D2++ SOC deeper check (local file-sink only)"
