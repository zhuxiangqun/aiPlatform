#!/usr/bin/env bash
# Evaluation D1 smoke — contract validate + GET /api/core/eval/healthz + protocol adapter.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

d1_require_python
ROOT="$(d1_repo_root)"; PKG="$(d1_repo_pkg)"
export PYTHONPATH="${ROOT}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}"
SMOKE_HOME="${AIPLAT_EVAL_SMOKE_HOME:-$(mktemp -d /tmp/aiplat-eval-smoke.XXXXXX)}"
export HOME="$SMOKE_HOME"; export AIPLAT_HOME="$SMOKE_HOME/.aiplat"
mkdir -p "$AIPLAT_HOME"
export AIPLAT_EXECUTION_DB_PATH="$AIPLAT_HOME/exec-smoke.sqlite3"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

python3 "$ROOT/reports/five-products/modules/evaluation/contracts/validate_sample.py"

export AIPLAT_EVAL_HEALTHZ_SCHEMA="$PKG/contracts/schemas/healthz.schema.json"
"$PY" - <<'PY'
import importlib, json, os
from pathlib import Path
import core.server as server
from fastapi.testclient import TestClient
from core.harness.evaluation.eval_protocol import SCHEMA_VERSION, to_eval_protocol_v0

schema = json.loads(Path(os.environ["AIPLAT_EVAL_HEALTHZ_SCHEMA"]).read_text(encoding="utf-8"))
assert schema["properties"]["product_id"]["const"] == "evaluation"
proto = to_eval_protocol_v0(
    task_id="d1-smoke", target_kind="skill", target_ref="fixture", status="passed", suite="smoke"
)
assert proto["schema_version"] == SCHEMA_VERSION
importlib.reload(server)
with TestClient(server.app) as client:
    r = client.get("/api/core/eval/healthz")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("product_id") == "evaluation", data
    assert data.get("capability_id") == "evaluation", data
    assert data.get("deploy_unit") == "central", data
    assert data.get("protocol") == "eval.protocol.v0", data
    assert data.get("status") in {"ok", "degraded", "fail"}, data
    print(json.dumps({"healthz": data["status"], "protocol": data.get("protocol")}, ensure_ascii=False))
    print("OK evaluation D1 smoke")
PY
echo "PASS: Evaluation D1 smoke HOME=$SMOKE_HOME"
