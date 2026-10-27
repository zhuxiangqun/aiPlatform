#!/usr/bin/env bash
# Gate3 Pi Thin pilot — smoke in an isolated env (ADR-08 / GATE3_PI_THIN_PILOT.md).
# Does not start platform/core control plane. Exits non-zero if AIPLAT_ENTERPRISE=1.
#
# GATE3_PI_THIN_PHASE=a (default): stub smoke against fixtures/sample-app
# GATE3_PI_THIN_PHASE=b: export_pi_bundle → smoke + AIPLAT_SLICE_EVIDENCE assert
# GATE3_PI_THIN_PHASE=c: b → ingest_slice_evidence_from_jsonl → diagnosis report
# GATE3_PI_THIN_PHASE=d: c → FDE slice signoff bind report_id (SCENE F1)
# GATE3_PI_THIN_PHASE=e: materialize lock-service sample → d chain (Phase E)
# GATE3_PI_THIN_PHASE=f: c → HTTP acceptance/signoff via ⑥b preflight (ASGI TestClient)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${GATE3_PI_THIN_ENV:-$ROOT/.env.gate3-pi-thin}"
EXAMPLE="$SCRIPT_DIR/gate3_pi_thin.env.example"
PHASE="${GATE3_PI_THIN_PHASE:-a}"

# Prefer repo venv (3.11+) for platform HTTP / CoreFacade; fall back to python3.
resolve_gate3_python() {
  if [[ -n "${GATE3_PI_THIN_PYTHON:-}" ]]; then
    echo "$GATE3_PI_THIN_PYTHON"
  elif [[ -x "$REPO/.venv/bin/python" ]]; then
    echo "$REPO/.venv/bin/python"
  else
    echo "python3"
  fi
}

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$EXAMPLE" ]]; then
    echo "NOTE: $ENV_FILE missing — loading example defaults from $EXAMPLE"
    ENV_FILE="$EXAMPLE"
  else
    echo "ERROR: missing $ENV_FILE and $EXAMPLE" >&2
    exit 2
  fi
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
  echo "ERROR: Gate3 Pi Thin pilot must not run with AIPLAT_ENTERPRISE=1 (control-plane bleed)." >&2
  exit 3
fi

export AIPLAT_HTTP_STUB="${AIPLAT_HTTP_STUB:-1}"
export AIPLAT_HTTP_PORT="${AIPLAT_HTTP_PORT:-18787}"
export AIPLAT_HTTP_API_KEY="${AIPLAT_HTTP_API_KEY:-gate3-pi-thin-pilot-key}"

run_phase_b() {
  local SAMPLE="${GATE3_PI_THIN_SAMPLE:-$ROOT/fixtures/sample-app}"
  local EXPORT_DIR="${GATE3_PI_THIN_EXPORT:-/tmp/aiplat-gate3-export-sample}"
  EVIDENCE_PATH="${AIPLAT_SLICE_EVIDENCE_PATH:-/tmp/aiplat-gate3-phase-b-evidence.jsonl}"
  mkdir -p "$EXPORT_DIR" "$(dirname "$EVIDENCE_PATH")"
  rm -f "$EVIDENCE_PATH"
  echo "Gate3 Phase B: export_pi_bundle $SAMPLE → $EXPORT_DIR"
  python3 "$REPO/scripts/export_pi_bundle.py" --app-home "$SAMPLE" --out "$EXPORT_DIR"
  export AIPLAT_APP_HOME="$EXPORT_DIR"
  export AIPLAT_SLICE_EVIDENCE=1
  export AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH"
  export AIPLAT_SLICE_SCENARIO_ID="${AIPLAT_SLICE_SCENARIO_ID:-fp-customer-lock-service-bundle-pi-diag-001}"
  export AIPLAT_SLICE_BUNDLE_VERSION="${AIPLAT_SLICE_BUNDLE_VERSION:-gate3-phase-b}"
  export AIPLAT_SLICE_RUNTIME_VERSION="${AIPLAT_SLICE_RUNTIME_VERSION:-pi-thin-gate3-b}"
  echo "Gate3 Pi Thin pilot phase=b stub=$AIPLAT_HTTP_STUB port=$AIPLAT_HTTP_PORT app=$AIPLAT_APP_HOME evidence=$EVIDENCE_PATH"
  bash "$ROOT/scripts/http_smoke.sh"
  if [[ ! -s "$EVIDENCE_PATH" ]]; then
    echo "ERROR: Phase B evidence file missing or empty: $EVIDENCE_PATH" >&2
    return 4
  fi
  if ! grep -q 'fp-customer-lock-service-bundle-pi-diag-001' "$EVIDENCE_PATH"; then
    echo "ERROR: Phase B evidence missing scenario_id" >&2
    return 5
  fi
  if ! grep -q 'http_chat' "$EVIDENCE_PATH"; then
    echo "ERROR: Phase B evidence missing http_chat event" >&2
    return 6
  fi
  echo "PASS: Gate3 Phase B (exported bundle + slice evidence)"
  return 0
}

run_phase_c_python() {
  PYTHONPATH="${REPO}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import json
import os
import sys

from core.apps.fde.service.slice_evidence import (
    build_slice_diagnosis_report,
    ingest_slice_evidence_from_jsonl,
)

path = os.environ["AIPLAT_SLICE_EVIDENCE_PATH"]
sid = os.environ.get("AIPLAT_SLICE_SCENARIO_ID", "fp-customer-lock-service-bundle-pi-diag-001")
# assumed_reachable=True is a pilot assumption (not a live control-plane probe).
ing = ingest_slice_evidence_from_jsonl(path=path, scenario_id=sid, assumed_reachable=True)
if not ing.get("ok"):
    print("ERROR: ingest failed:", json.dumps(ing, ensure_ascii=False), file=sys.stderr)
    sys.exit(7)
rep = build_slice_diagnosis_report(scenario_id=sid, ingest_id=ing["ingest_id"])
if not rep.get("ok"):
    print("ERROR: report failed:", json.dumps(rep, ensure_ascii=False), file=sys.stderr)
    sys.exit(8)
if rep.get("status") != "ok" or not rep.get("diagnosis_ok"):
    print("ERROR: diagnosis not ok:", json.dumps(rep, ensure_ascii=False), file=sys.stderr)
    sys.exit(9)
rid = rep.get("report_id")
print(
    "PASS: Gate3 Phase C ingest_id=%s report_id=%s status=%s"
    % (ing.get("ingest_id"), rid, rep.get("status"))
)
print("REPORT_ID=%s" % rid)
PY
}

materialize_lock_service_sample() {
  # Copy sample-app → /tmp and stamp domain/scene (no deep tree committed to git).
  local SRC="${GATE3_PI_THIN_BASE_SAMPLE:-$ROOT/fixtures/sample-app}"
  local DST="${GATE3_PI_THIN_SAMPLE:-/tmp/aiplat-gate3-lock-service-sample}"
  rm -rf "$DST"
  mkdir -p "$DST"
  cp -a "$SRC/." "$DST/"
  PYTHONPATH= python3 - "$DST" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
man = root / "agent_manifest.json"
data = json.loads(man.read_text(encoding="utf-8"))
data["domain_id"] = "lock-service"
data["scene_id"] = "fp-customer-lock-service-bundle-pi-diag-001"
data["customer_org"] = "江苏锁安"
man.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
agent = root / "agents" / "demo_agent" / "AGENT.md"
if agent.is_file():
    text = agent.read_text(encoding="utf-8")
    if "lock-service" not in text:
        agent.write_text(
            text.rstrip()
            + "\n\n## Scene\n\nDomain `lock-service` / 江苏锁安 / `fp-customer-lock-service-bundle-pi-diag-001`.\n",
            encoding="utf-8",
        )
print(root)
PY
  export GATE3_PI_THIN_SAMPLE="$DST"
  echo "Gate3: materialized lock-service sample at $DST"
}

if [[ "$PHASE" == "b" || "$PHASE" == "B" ]]; then
  # Optional: same lock-service fixture as Phase E (for disconnect / evidence-only paths).
  if [[ "${GATE3_PI_THIN_LOCK_SAMPLE:-0}" == "1" ]]; then
    materialize_lock_service_sample
  fi
  run_phase_b
  exit $?
fi

if [[ "$PHASE" == "c" || "$PHASE" == "C" ]]; then
  export AIPLAT_HOME="${GATE3_PI_THIN_AIPLAT_HOME:-/tmp/aiplat-gate3-phase-c-home}"
  mkdir -p "$AIPLAT_HOME"
  EVIDENCE_PATH="${AIPLAT_SLICE_EVIDENCE_PATH:-/tmp/aiplat-gate3-phase-c-evidence.jsonl}"
  export AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH"
  run_phase_b
  echo "Gate3 Phase C: ingest JSONL → diagnosis MVP ($EVIDENCE_PATH)"
  run_phase_c_python
  exit $?
fi

if [[ "$PHASE" == "e" || "$PHASE" == "E" ]]; then
  materialize_lock_service_sample
  export AIPLAT_HOME="${GATE3_PI_THIN_AIPLAT_HOME:-/tmp/aiplat-gate3-phase-e-home}"
  mkdir -p "$AIPLAT_HOME"
  EVIDENCE_PATH="${AIPLAT_SLICE_EVIDENCE_PATH:-/tmp/aiplat-gate3-phase-e-evidence.jsonl}"
  export AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH"
  export AIPLAT_SLICE_BUNDLE_VERSION="${AIPLAT_SLICE_BUNDLE_VERSION:-gate3-phase-e-lock-service}"
  run_phase_b
  if ! grep -q 'lock-service' "$AIPLAT_APP_HOME/agent_manifest.json" 2>/dev/null; then
    echo "ERROR: Phase E export missing domain_id=lock-service in agent_manifest.json" >&2
    exit 13
  fi
  echo "Gate3 Phase E: lock-service Bundle → Phase C/D bind"
  C_OUT="$(run_phase_c_python)"
  echo "$C_OUT"
  REPORT_ID="$(printf '%s\n' "$C_OUT" | awk -F= '/^REPORT_ID=/{print $2}' | tail -1)"
  if [[ -z "$REPORT_ID" ]]; then
    echo "ERROR: Phase E missing REPORT_ID from Phase C" >&2
    exit 10
  fi
  export GATE3_PHASE_D_REPORT_ID="$REPORT_ID"
  PYTHONPATH="${REPO}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import json
import os
import sys
import time
from pathlib import Path

from core.apps.fde.service.slice_evidence import validate_slice_signoff_reports

sid = os.environ.get("AIPLAT_SLICE_SCENARIO_ID", "fp-customer-lock-service-bundle-pi-diag-001")
rid = os.environ["GATE3_PHASE_D_REPORT_ID"]
home = Path(os.environ["AIPLAT_HOME"])
manifest = Path(os.environ["AIPLAT_APP_HOME"]) / "agent_manifest.json"
meta = json.loads(manifest.read_text(encoding="utf-8"))
if meta.get("domain_id") != "lock-service":
    print("ERROR: manifest domain_id not lock-service:", meta.get("domain_id"), file=sys.stderr)
    sys.exit(13)

neg = validate_slice_signoff_reports({"scenario_id": sid, "for_slice": True})
if neg.get("ok"):
    print("ERROR: expected signoff without report_id to fail", json.dumps(neg), file=sys.stderr)
    sys.exit(11)

pos = validate_slice_signoff_reports(
    {"scenario_id": sid, "for_slice": True, "evidence_report_ids": [rid]}
)
if not pos.get("ok"):
    print("ERROR: signoff with report_id failed:", json.dumps(pos, ensure_ascii=False), file=sys.stderr)
    sys.exit(12)

acc_dir = home / "five_products_slice" / "acceptance"
acc_dir.mkdir(parents=True, exist_ok=True)
fid = "%s-%d" % (sid, int(time.time()))
record = {
    "ok": True,
    "phase": "gate3-e",
    "domain_id": "lock-service",
    "scenario_id": sid,
    "spec_id": sid,
    "acceptance_decision": "accepted",
    "evidence_report_ids": list(pos.get("report_ids") or [rid]),
    "for_slice": True,
    "signed_by": "gate3-phase-e-pilot",
    "notes": "lock-service fixture Bundle → diagnosis → FDE bind",
    "record_id": fid,
}
path = acc_dir / ("%s.json" % fid)
path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("PASS: Gate3 Phase E lock-service report_id=%s record=%s" % (rid, path))
PY
  exit $?
fi

if [[ "$PHASE" == "d" || "$PHASE" == "D" ]]; then
  export AIPLAT_HOME="${GATE3_PI_THIN_AIPLAT_HOME:-/tmp/aiplat-gate3-phase-d-home}"
  mkdir -p "$AIPLAT_HOME"
  EVIDENCE_PATH="${AIPLAT_SLICE_EVIDENCE_PATH:-/tmp/aiplat-gate3-phase-d-evidence.jsonl}"
  export AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH"
  run_phase_b
  echo "Gate3 Phase D: Phase C then FDE signoff bind report_id"
  C_OUT="$(run_phase_c_python)"
  echo "$C_OUT"
  REPORT_ID="$(printf '%s\n' "$C_OUT" | awk -F= '/^REPORT_ID=/{print $2}' | tail -1)"
  if [[ -z "$REPORT_ID" ]]; then
    echo "ERROR: Phase D missing REPORT_ID from Phase C" >&2
    exit 10
  fi
  export GATE3_PHASE_D_REPORT_ID="$REPORT_ID"
  PYTHONPATH="${REPO}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import json
import os
import sys
import time
from pathlib import Path

from core.apps.fde.service.slice_evidence import validate_slice_signoff_reports

sid = os.environ.get("AIPLAT_SLICE_SCENARIO_ID", "fp-customer-lock-service-bundle-pi-diag-001")
rid = os.environ["GATE3_PHASE_D_REPORT_ID"]
home = Path(os.environ["AIPLAT_HOME"])

neg = validate_slice_signoff_reports({"scenario_id": sid, "for_slice": True})
if neg.get("ok"):
    print("ERROR: expected signoff without report_id to fail", json.dumps(neg), file=sys.stderr)
    sys.exit(11)

pos = validate_slice_signoff_reports(
    {
        "scenario_id": sid,
        "for_slice": True,
        "evidence_report_ids": [rid],
    }
)
if not pos.get("ok"):
    print("ERROR: signoff with report_id failed:", json.dumps(pos, ensure_ascii=False), file=sys.stderr)
    sys.exit(12)

acc_dir = home / "five_products_slice" / "acceptance"
acc_dir.mkdir(parents=True, exist_ok=True)
fid = "%s-%d" % (sid, int(time.time()))
record = {
    "ok": True,
    "phase": "gate3-d",
    "scenario_id": sid,
    "spec_id": sid,
    "acceptance_decision": "accepted",
    "evidence_report_ids": list(pos.get("report_ids") or [rid]),
    "for_slice": True,
    "signed_by": "gate3-phase-d-pilot",
    "notes": "sandbox bind record (no HTTP preflight); SCENE F1",
    "record_id": fid,
}
path = acc_dir / ("%s.json" % fid)
path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("PASS: Gate3 Phase D bound report_id=%s record=%s" % (rid, path))
PY
  exit $?
fi

if [[ "$PHASE" == "f" || "$PHASE" == "F" ]]; then
  export AIPLAT_HOME="${GATE3_PI_THIN_AIPLAT_HOME:-/tmp/aiplat-gate3-phase-f-home}"
  mkdir -p "$AIPLAT_HOME"
  # Always under this phase home (ignore ambient AIPLAT_ACCEPTANCE_DIR).
  export AIPLAT_ACCEPTANCE_DIR="${GATE3_PI_THIN_ACCEPTANCE_DIR:-$AIPLAT_HOME/acceptance}"
  mkdir -p "$AIPLAT_ACCEPTANCE_DIR"
  EVIDENCE_PATH="${AIPLAT_SLICE_EVIDENCE_PATH:-/tmp/aiplat-gate3-phase-f-evidence.jsonl}"
  export AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH"
  export AIPLAT_SLICE_BUNDLE_VERSION="${AIPLAT_SLICE_BUNDLE_VERSION:-gate3-phase-f-http}"
  # Fresh home → no leftover ⑥b latest.json from prior runs
  rm -rf "$AIPLAT_HOME/fde_security_preflight"
  run_phase_b
  echo "Gate3 Phase F: Phase C then HTTP acceptance/signoff (⑥b preflight)"
  C_OUT="$(run_phase_c_python)"
  echo "$C_OUT"
  REPORT_ID="$(printf '%s\n' "$C_OUT" | awk -F= '/^REPORT_ID=/{print $2}' | tail -1)"
  if [[ -z "$REPORT_ID" ]]; then
    echo "ERROR: Phase F missing REPORT_ID from Phase C" >&2
    exit 10
  fi
  export GATE3_PHASE_F_REPORT_ID="$REPORT_ID"
  export GATE3_PI_THIN_REPO="$REPO"
  GATE3_PY="$(resolve_gate3_python)"
  echo "Gate3 Phase F: HTTP ASGI client via $GATE3_PY"
  PYTHONPATH="${REPO}/aiPlat-core:${REPO}/aiPlat-platform${PYTHONPATH:+:$PYTHONPATH}" \
    "$GATE3_PY" - <<'PY'
import importlib.util
import os
import sys
import types
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.apps.fde.service.security_preflight import save_preflight_run

sid = os.environ.get("AIPLAT_SLICE_SCENARIO_ID", "fp-customer-lock-service-bundle-pi-diag-001")
rid = os.environ["GATE3_PHASE_F_REPORT_ID"]
repo = Path(os.environ["GATE3_PI_THIN_REPO"]).resolve()
plat_api = repo / "aiPlat-platform" / "apps" / "fde" / "api"
# Load acceptance router without apps.fde package __init__ (heavy / version-sensitive).
apps = types.ModuleType("apps")
sys.modules["apps"] = apps
apps_fde = types.ModuleType("apps.fde")
apps_fde.__path__ = [str(plat_api.parent)]
sys.modules["apps.fde"] = apps_fde
apps_fde_api = types.ModuleType("apps.fde.api")
apps_fde_api.__path__ = [str(plat_api)]
sys.modules["apps.fde.api"] = apps_fde_api

def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

_load("apps.fde.api.schemas", plat_api / "schemas.py")
acc = _load("apps.fde.api.fde_acceptance", plat_api / "fde_acceptance.py")

app = FastAPI()
app.include_router(acc.router, prefix="/api/platform/apps/fde")
client = TestClient(app, raise_server_exceptions=False)
url = "/api/platform/apps/fde/acceptance/signoff"
base = {
    "spec_id": sid,
    "scenario_id": sid,
    "for_slice": True,
    "signed_by": "gate3-phase-f-pilot",
    "notes": "HTTP ⑥b preflight + slice report_id",
}

r0 = client.post(url, json={**base, "evidence_report_ids": [rid]})
if r0.status_code != 409:
    print("ERROR: expected 409 without ⑥b, got", r0.status_code, r0.text[:400], file=sys.stderr)
    sys.exit(14)
detail0 = (r0.json() or {}).get("detail") or {}
if detail0.get("error") != "preflight_gate_blocked":
    print("ERROR: expected preflight_gate_blocked:", detail0, file=sys.stderr)
    sys.exit(14)

save_preflight_run(
    dry_run={"status": "ok", "phase": "B", "security_report": {"findings": []}},
    actor="gate3-phase-f-pilot",
)

r1 = client.post(url, json=base)  # ⑥b ok, no report_id
if r1.status_code != 409:
    print("ERROR: expected 409 without report_id, got", r1.status_code, r1.text[:400], file=sys.stderr)
    sys.exit(15)
detail1 = (r1.json() or {}).get("detail") or {}
if "slice" not in str(detail1.get("error") or "").lower() and "evidence_report" not in str(detail1):
    print("ERROR: expected slice report gate:", detail1, file=sys.stderr)
    sys.exit(15)

r2 = client.post(url, json={**base, "evidence_report_ids": [rid]})
if r2.status_code != 200:
    print("ERROR: expected 200 signed_off, got", r2.status_code, r2.text[:500], file=sys.stderr)
    sys.exit(16)
body2 = r2.json() or {}
if body2.get("status") != "signed_off":
    print("ERROR: status not signed_off:", body2, file=sys.stderr)
    sys.exit(16)

acc_dir = Path(os.environ["AIPLAT_ACCEPTANCE_DIR"])
files = sorted(acc_dir.glob("%s-*.json" % sid))
if not files:
    print("ERROR: HTTP signoff did not persist under", acc_dir, file=sys.stderr)
    sys.exit(17)
print(
    "PASS: Gate3 Phase F HTTP signoff report_id=%s status=%s record=%s"
    % (rid, body2.get("status"), files[-1])
)
PY
  exit $?
fi

if [[ -z "${AIPLAT_APP_HOME:-}" ]]; then
  export AIPLAT_APP_HOME="$ROOT/fixtures/sample-app"
fi

echo "Gate3 Pi Thin pilot phase=a stub=$AIPLAT_HTTP_STUB port=$AIPLAT_HTTP_PORT app=$AIPLAT_APP_HOME enterprise=${AIPLAT_ENTERPRISE:-0}"
exec bash "$ROOT/scripts/http_smoke.sh"
