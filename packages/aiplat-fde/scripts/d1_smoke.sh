#!/usr/bin/env bash
# FDE Field D1 PREP smoke — contracts + CoreFacade healthz (sandbox-safe).
# Optional live ADR-09 probe: AIPLAT_FDE_SMOKE_LIVE=1
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

d1_require_python
ROOT="$(d1_repo_root)"; PKG="$(d1_repo_pkg)"; PREFIX="$(d1_prefix)"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

python3 "$ROOT/reports/five-products/modules/fde/contracts/validate_sample.py"

export AIPLAT_FDE_HEALTHZ_SCHEMA="$PKG/contracts/schemas/healthz.schema.json"
export AIPLAT_FDE_EVIDENCE_SCHEMA="$PKG/contracts/schemas/evidence_export.schema.json"
export PYTHONPATH="${ROOT}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}"

"$PY" - <<'PY'
import json
import os
from pathlib import Path

hz_schema = json.loads(Path(os.environ["AIPLAT_FDE_HEALTHZ_SCHEMA"]).read_text(encoding="utf-8"))
ev_schema = json.loads(Path(os.environ["AIPLAT_FDE_EVIDENCE_SCHEMA"]).read_text(encoding="utf-8"))
assert hz_schema["properties"]["product_id"]["const"] == "fde"
assert hz_schema["properties"]["deploy_unit"]["const"] == "field"

from core.api.core_facade import fde_healthz_payload

healthz = fde_healthz_payload()
for k in hz_schema.get("required") or []:
    assert k in healthz, k
assert healthz["status"] in hz_schema["properties"]["status"]["enum"]
assert healthz.get("product_id") == "fde"
assert healthz.get("version") == "0.1.0"
assert healthz.get("production_field") is True
assert healthz.get("field_d1_adr") == "accepted"

try:
    import jsonschema
    jsonschema.validate(healthz, hz_schema)
    print("OK jsonschema healthz facade-shape")
except ImportError:
    print("OK fallback healthz facade-shape")

evidence = {
    "schema_version": "fde.evidence.v0",
    "scenario_id": "smoke",
    "exported_at": "2026-10-30T00:00:00Z",
    "report_id": "rep-smoke",
    "items": [{"kind": "diagnosis_report", "ref": "rep-smoke"}],
}
for k in ev_schema.get("required") or []:
    assert k in evidence, k
print("OK evidence shape")
print(json.dumps({"product_id": "fde", "version": healthz.get("version"), "mode": healthz.get("mode"), "production_field": healthz.get("production_field")}, ensure_ascii=False))
PY

if [[ -f "$PREFIX/INSTALL_META.json" ]]; then
  python3 -c "import json; m=json.load(open('$PREFIX/INSTALL_META.json')); assert m.get('production_field') is True; assert m.get('field_d1_adr')=='accepted'; print('OK INSTALL_META accepted gate')"
else
  echo "NOTE: no INSTALL_META yet (run d1_install for meta gate)"
fi

if [[ "${AIPLAT_FDE_SMOKE_LIVE:-0}" == "1" ]]; then
  export ADR09_FDE_AIPLAT_HOME="${AIPLAT_FDE_SMOKE_HOME:-$(mktemp -d /tmp/aiplat-fde-smoke.XXXXXX)}"
  export AIPLAT_HOME="$ADR09_FDE_AIPLAT_HOME"
  mkdir -p "$AIPLAT_HOME"
  export ADR09_FDE_HEALTH_PORT="${AIPLAT_FDE_SMOKE_PORT:-$((29100 + RANDOM % 500))}"
  export AIPLAT_ENTERPRISE=0
  export AIPLAT_FDE_OPTIONAL_SPLIT=1
  bash "$ROOT/scripts/adr09_fde_optional_phase_health.sh"
fi

echo "PASS: FDE Field D1 smoke (ADR Accepted; production_field=true)"
