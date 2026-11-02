#!/usr/bin/env bash
# B3-L local closeout — sandbox stub/docker + dual-read evidence.
# NEVER sets process_split_authorized=true. NOT staging authorize. NOT B4/B6.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_B3L_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
WORK="${AIPLAT_EVAL_B3L_CLOSEOUT_WORK:-$(mktemp -d /tmp/aiplat-eval-b3l-closeout.XXXXXX)}"
mkdir -p "$EVID_DIR" "$WORK"

export AIPLAT_EVAL_DB_URL="${AIPLAT_EVAL_DB_URL:-sqlite:///${WORK}/eval_b3l.sqlite3}"
export AIPLAT_EVAL_REQUIRE_AUTH="${AIPLAT_EVAL_REQUIRE_AUTH:-1}"
export AIPLAT_EVAL_JWT_SECRET="${AIPLAT_EVAL_JWT_SECRET:-aiplat-eval-local-dev-secret}"
export AIPLAT_EVAL_WORKER_ID="${AIPLAT_EVAL_WORKER_ID:-worker-b3l-closeout}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

# Fake docker for offline closeout (no daemon required).
FAKE_DOCKER="${WORK}/fake-docker"
cat >"$FAKE_DOCKER" <<'SH'
#!/bin/sh
if [ "$1" != "run" ]; then echo 'only run' >&2; exit 2; fi
shift
while [ $# -gt 0 ]; do
  case "$1" in
    --*) shift; continue ;;
    alpine:*|busybox*) shift; break ;;
    *) shift; continue ;;
  esac
done
if [ "$1" = "false" ]; then echo fail >&2; exit 1; fi
printf '%s' "$*"
exit 0
SH
chmod +x "$FAKE_DOCKER"
export AIPLAT_EVAL_DOCKER_BIN="$FAKE_DOCKER"
export AIPLAT_EVAL_B3L_EVIDENCE_DIR="$EVID_DIR"
export AIPLAT_EVAL_B3L_STAMP="$STAMP"

echo "B3-L closeout workdir=$WORK db=$AIPLAT_EVAL_DB_URL"

bash "$ROOT/scripts/migrate_local.sh" >/dev/null

PYTHONPATH=. python3 -m pytest \
  tests/test_b3l_sandbox_local_stub.py \
  tests/test_b3l_sandbox_docker_cli.py \
  tests/test_b3l_skill_suite_fixture.py \
  tests/test_b3l_dual_read.py \
  tests/test_b2l_allowlist_enqueue.py \
  tests/test_prompt_eval_llm.py::test_llm_off_by_default \
  tests/test_prompt_eval_llm.py::test_prompt_eval_stub_fills_actual \
  tests/test_prompt_eval_llm.py::test_prompt_eval_still_fail_closed_without_llm \
  -q --tb=line

# dual-read drill nested workdir
AIPLAT_EVAL_B3L_WORK="${WORK}/dual" \
AIPLAT_EVAL_B3L_EVIDENCE_DIR="$EVID_DIR" \
  bash "$ROOT/scripts/b3l_dual_read_drill.sh"

python3 - <<'PY'
import ast
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import mint_local_token
from app.config import EvalServiceConfig
from app.main import create_app
from app.store.jobs import get_job
from app.worker.loop import run_worker_loop

# import guard
root = Path("app")
forbidden = ("core.harness", "core.api.core_facade", "aiPlat_core", "aiplat_core")
for path in root.rglob("*.py"):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                assert not any(name == p or name.startswith(p + ".") for p in forbidden), path
        elif isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            assert not any(mod == p or mod.startswith(p + ".") for p in forbidden), (path, mod)
print("import_guard ok")

db = os.environ["AIPLAT_EVAL_DB_URL"]
os.environ["AIPLAT_EVAL_SANDBOX_BACKEND"] = "docker"
cfg = EvalServiceConfig(
    mode="standalone",
    host="127.0.0.1",
    port=8010,
    db_url=db,
    version="0.1.0",
    protocol="eval.protocol.v0",
    require_auth=True,
)
client = TestClient(create_app(cfg))
headers = {"Authorization": f"Bearer {mint_local_token(tenant_id='tenant-b3l')}"}

# live skill tools still denied; bare body fail-closed
r = client.post(
    "/api/platform/apps/eval/skill-evals/suites/s1/run",
    headers=headers,
    json={"tools": ["shell"]},
)
assert r.status_code == 422 and r.json()["error"]["code"] == "sandbox_required", r.text
r = client.post("/api/platform/apps/eval/skill-evals/suites/s1/run", headers=headers, json={})
assert r.status_code == 422 and r.json()["error"]["code"] == "sandbox_required", r.text

# http_probe admitted
r = client.post(
    "/api/platform/apps/eval/probes/http",
    headers=headers,
    json={"idempotency_key": "b3l-http", "url": "https://example.com", "method": "GET"},
)
assert r.status_code == 202, r.text
http_job = r.json()["job_id"]

# cli_probe admitted with fake docker
r = client.post(
    "/api/platform/apps/eval/probes/cli",
    headers=headers,
    json={"idempotency_key": "b3l-cli", "argv": ["true"]},
)
assert r.status_code == 202, r.text
cli_job = r.json()["job_id"]

hz = client.get("/healthz").json()
assert hz["process_split_authorized"] is False, hz
assert hz.get("sandbox_real_isolation") is False, hz
assert hz.get("b3l_sandbox") is True, hz

loop = run_worker_loop(
    db,
    worker_id=os.environ["AIPLAT_EVAL_WORKER_ID"],
    idle_sleep_s=0,
    max_jobs=2,
    max_idle_rounds=3,
)
assert loop.processed == 2, (loop.processed, loop.outcomes, loop.stopped_reason)
http_stored = get_job(db, http_job)
cli_stored = get_job(db, cli_job)
assert http_stored and http_stored["status"] == "succeeded", http_stored
assert cli_stored and cli_stored["status"] == "succeeded", cli_stored

evid = Path(os.environ.get("AIPLAT_EVAL_B3L_EVIDENCE_DIR") or "docs/a3/drills")
stamp = os.environ.get("AIPLAT_EVAL_B3L_STAMP") or ""
if not stamp:
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
out = {
    "schema": "eval.b3l.closeout.v0",
    "product_id": "evaluation",
    "phase": "B3-L",
    "environment": "local",
    "process_split_authorized": False,
    "staging_ready": False,
    "sandbox_real_isolation": False,
    "accuracy_claim": False,
    "recorded_at": stamp,
    "checks": {
        "local_stub_http_probe": True,
        "docker_cli_probe_fake_bin": True,
        "skill_suite_still_denied": True,
        "dual_read_drill": True,
        "optional_llm_tests": True,
        "import_guard_no_core_harness": True,
        "microvm": False,
        "skill_suite_real_tools": False,
    },
    "honesty": "B3-L engineering closeout — container prototype + dual-read fixture; not microVM; not production backfill; not authorize",
}
path = evid / f"local-eval-b3l-closeout-{stamp}.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"closeout": "ok", "evidence": str(path)}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status | tee "$WORK/authorize_status.txt" >/dev/null
if grep -qiE 'process_split_authorized["[:space:]]*[:=][[:space:]]*true|authorized[[:space:]]*=[[:space:]]*true' "$WORK/authorize_status.txt" 2>/dev/null; then
  echo "REFUSE: authorize flipped true during B3-L closeout" >&2
  exit 1
fi

echo "B3-L local closeout PASS (process_split_authorized=false)"
