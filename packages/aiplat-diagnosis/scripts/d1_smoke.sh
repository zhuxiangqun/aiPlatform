#!/usr/bin/env bash
# Diagnosis D1 smoke — contract validate + facade health + honesty locks.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

d1_require_python
ROOT="$(d1_repo_root)"; PKG="$(d1_repo_pkg)"
export PYTHONPATH="${ROOT}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}"
SMOKE_HOME="${AIPLAT_DIAGNOSIS_SMOKE_HOME:-$(mktemp -d /tmp/aiplat-diagnosis-smoke.XXXXXX)}"
export HOME="$SMOKE_HOME"; export AIPLAT_HOME="$SMOKE_HOME/.aiplat"
mkdir -p "$AIPLAT_HOME"
export AIPLAT_EXECUTION_DB_PATH="$AIPLAT_HOME/exec-smoke.sqlite3"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

python3 "$ROOT/reports/five-products/modules/diagnosis/contracts/validate_sample.py"

export AIPLAT_DIAGNOSIS_HEALTHZ_SCHEMA="$PKG/contracts/schemas/healthz.schema.json"
"$PY" - <<'PY'
import json
import os
from pathlib import Path

from core.api.core_facade import diagnosis_health

schema = json.loads(Path(os.environ["AIPLAT_DIAGNOSIS_HEALTHZ_SCHEMA"]).read_text(encoding="utf-8"))
assert schema["properties"]["product_id"]["const"] == "diagnosis"
assert schema["properties"]["deploy_unit"]["const"] == "central"

data = diagnosis_health(tenant_id="")
assert data.get("product_id") == "diagnosis", data
assert data.get("capability_id") == "diagnosis", data
assert data.get("deploy_unit") == "central", data
assert data.get("status") in {"ok", "degraded", "fail"}, data
assert data.get("accuracy_claim") is False, data
assert data.get("auto_execute") is False, data
assert data.get("process_split_authorized") is False, data
print(json.dumps({"healthz": data["status"], "case_count": data.get("case_count")}, ensure_ascii=False))
print("OK diagnosis D1 smoke")
PY
echo "PASS: Diagnosis D1 smoke HOME=$SMOKE_HOME"
