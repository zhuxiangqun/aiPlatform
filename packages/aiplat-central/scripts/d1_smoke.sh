#!/usr/bin/env bash
# Central D1 smoke — ephemeral core /api/core/healthz (product_id=aiplat).
# Starts an in-process TestClient; no long-running server required.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

d1_require_python
ROOT="$(d1_repo_root)"
PKG="$(d1_repo_pkg)"
PREFIX="$(d1_prefix)"

export PYTHONPATH="${ROOT}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}"
SMOKE_HOME="${AIPLAT_CENTRAL_SMOKE_HOME:-$(mktemp -d /tmp/aiplat-central-smoke.XXXXXX)}"
export HOME="$SMOKE_HOME"
export AIPLAT_HOME="$SMOKE_HOME/.aiplat"
mkdir -p "$AIPLAT_HOME"
export AIPLAT_EXECUTION_DB_PATH="$AIPLAT_HOME/exec-smoke.sqlite3"

PY=python3
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
fi

SCHEMA="$PKG/contracts/schemas/healthz.schema.json"
export AIPLAT_CENTRAL_HEALTHZ_SCHEMA="$SCHEMA"

"$PY" - <<'PY'
import importlib
import json
import os
from pathlib import Path

import core.server as server
from fastapi.testclient import TestClient

schema_path = Path(os.environ["AIPLAT_CENTRAL_HEALTHZ_SCHEMA"])
schema = json.loads(schema_path.read_text(encoding="utf-8"))
assert schema["properties"]["product_id"]["const"] == "aiplat"

importlib.reload(server)
with TestClient(server.app) as client:
    r = client.get("/api/core/healthz")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") in {"ok", "degraded", "fail"}, data
    assert data.get("product_id") == "aiplat", data
    assert data.get("capability_id") == "aiplat", data
    assert data.get("deploy_unit") == "central", data
    assert data.get("control_plane", {}).get("schema_version") == "aiplat.control.v0", data
    for k in schema.get("required") or []:
        assert k in data, k
    print(json.dumps({
        "status": data["status"],
        "product_id": data["product_id"],
        "hosted": data.get("hosted"),
    }, ensure_ascii=False))
    print("OK healthz contract")
PY

if [[ -f "$PREFIX/INSTALL_META.json" ]]; then
  echo "Installed meta: $(cat "$PREFIX/INSTALL_META.json")"
fi

echo "PASS: aiPlat Central D1 smoke (healthz) HOME=$SMOKE_HOME"
