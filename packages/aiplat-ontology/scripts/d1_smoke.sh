#!/usr/bin/env bash
# Ontology D1 smoke — contract validate + GET /api/core/ontology/healthz.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

d1_require_python
ROOT="$(d1_repo_root)"; PKG="$(d1_repo_pkg)"
export PYTHONPATH="${ROOT}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}"
SMOKE_HOME="${AIPLAT_ONTOLOGY_SMOKE_HOME:-$(mktemp -d /tmp/aiplat-ontology-smoke.XXXXXX)}"
export HOME="$SMOKE_HOME"; export AIPLAT_HOME="$SMOKE_HOME/.aiplat"
mkdir -p "$AIPLAT_HOME"
export AIPLAT_EXECUTION_DB_PATH="$AIPLAT_HOME/exec-smoke.sqlite3"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

# Module contract sample
python3 "$ROOT/reports/five-products/modules/ontology/contracts/validate_sample.py"

export AIPLAT_ONTOLOGY_HEALTHZ_SCHEMA="$PKG/contracts/schemas/healthz.schema.json"
"$PY" - <<'PY'
import importlib, json, os
from pathlib import Path
import core.server as server
from fastapi.testclient import TestClient

schema = json.loads(Path(os.environ["AIPLAT_ONTOLOGY_HEALTHZ_SCHEMA"]).read_text(encoding="utf-8"))
assert schema["properties"]["product_id"]["const"] == "ontology"
importlib.reload(server)
with TestClient(server.app) as client:
    r = client.get("/api/core/ontology/healthz")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("product_id") == "ontology", data
    assert data.get("capability_id") == "ontology", data
    assert data.get("deploy_unit") == "central", data
    assert data.get("status") in {"ok", "degraded", "fail"}, data
    assert "domains" in data
    # envelope smoke on wiki pages
    r2 = client.get("/api/core/wiki/pages", params={"limit": 1})
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert "ontology_api" in body, body.keys()
    assert body["ontology_api"].get("schema_version") == "ontology.api.v0"
    print(json.dumps({"healthz": data["status"], "domains": data.get("domains")}, ensure_ascii=False))
    print("OK ontology D1 smoke")
PY
echo "PASS: Ontology D1 smoke HOME=$SMOKE_HOME"
