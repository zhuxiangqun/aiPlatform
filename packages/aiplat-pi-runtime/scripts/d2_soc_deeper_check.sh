#!/usr/bin/env bash
# Pi D2++ SOC deeper check — validates latest local soc-rehearsal JSON shape.
# Requires fixed fields: kind / severity / actor / environment=local.
# Never production_signed / authorize.
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

env = str(data.get("environment") or "")
if env != "local":
    errors.append(f"environment must be 'local' (got {env!r})")

for key in ("kind", "severity", "actor", "at"):
    if not data.get(key):
        errors.append(f"missing required field: {key}")

kind = str(data.get("kind") or "")
if "not_production" not in kind and kind != "pi_d3_soc_local_file_sink_not_production":
    if "production" in kind.lower() and "not_production" not in kind.lower():
        errors.append(f"kind looks production-ish: {kind!r}")

if data.get("production_soc") is True:
    errors.append("production_soc must not be true")
if data.get("production_signed") is True:
    errors.append("production_signed must not be true")
if data.get("outbound_network") is True:
    errors.append("outbound_network must be false for local file-sink")

sample = data.get("events_sample") or []
if not sample:
    errors.append("missing events_sample (D2++ fixed schema)")
else:
    ev = sample[0] if isinstance(sample, list) else sample
    for key in ("kind", "severity", "actor", "environment"):
        if key not in ev:
            errors.append(f"events_sample[0] missing {key}")
    if isinstance(ev, dict) and ev.get("environment") != "local":
        errors.append(f"events_sample environment must be local (got {ev.get('environment')!r})")
    if isinstance(ev, dict) and ev.get("outbound_network") is True:
        errors.append("events_sample outbound_network must be false")

text = p.read_text(encoding="utf-8")
if '"production_signed": true' in text:
    errors.append("production_signed must not be true in local soc rehearsal")
if "https://" in text or "http://" in text:
    # allow file:// only; ban webhook URLs in evidence
    if "http://" in text or "https://" in text:
        errors.append("HTTP(S) URL in local soc evidence (file-sink only)")

if errors:
    print("FAIL d2_soc_deeper_check:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print(
    f"OK d2_soc_deeper_check file={p} environment={env} "
    f"severity={data.get('severity')} actor={data.get('actor')}"
)
PY
pass "Pi D2++ SOC deeper check (local file-sink only)"
