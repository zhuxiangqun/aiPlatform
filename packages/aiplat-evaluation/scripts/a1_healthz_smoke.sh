#!/usr/bin/env bash
# A1 smoke: boot TestClient-equivalent via uvicorn briefly, or use in-process check.
# Prefer in-process pytest; this script hits a running server if already up.
set -euo pipefail

HOST="${AIPLAT_EVAL_HOST:-127.0.0.1}"
PORT="${AIPLAT_EVAL_PORT:-8010}"
BASE="http://${HOST}:${PORT}"

curl -fsS "${BASE}/healthz" | python3 -c '
import json,sys
d=json.load(sys.stdin)
assert d.get("product_id")=="evaluation", d
assert d.get("process_split_authorized") is False, d
assert d.get("status")=="ok", d
print("healthz ok", d.get("mode"), d.get("deploy_unit"))
'
curl -fsS "${BASE}/readyz" | python3 -c '
import json,sys
d=json.load(sys.stdin)
assert d.get("status")=="ready", d
assert d.get("process_split_authorized") is False, d
print("readyz ok")
'
echo "A1 smoke PASS"
