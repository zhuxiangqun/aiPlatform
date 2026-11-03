#!/usr/bin/env bash
# B2-L local closeout — allowlist enqueue + claim/execute + worker loop evidence.
# NEVER sets process_split_authorized=true. NOT staging authorize. NOT B3/B4.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_DIR="${AIPLAT_EVAL_B2L_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
WORK="${AIPLAT_EVAL_B2L_WORK:-$(mktemp -d /tmp/aiplat-eval-b2l-closeout.XXXXXX)}"
mkdir -p "$EVID_DIR" "$WORK"

export AIPLAT_EVAL_DB_URL="${AIPLAT_EVAL_DB_URL:-sqlite:///${WORK}/eval_b2l.sqlite3}"
export AIPLAT_EVAL_REQUIRE_AUTH="${AIPLAT_EVAL_REQUIRE_AUTH:-1}"
export AIPLAT_EVAL_JWT_SECRET="${AIPLAT_EVAL_JWT_SECRET:-aiplat-eval-local-dev-secret}"
export AIPLAT_EVAL_WORKER_ID="${AIPLAT_EVAL_WORKER_ID:-worker-b2l-closeout}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "B2-L closeout workdir=$WORK db=$AIPLAT_EVAL_DB_URL"

# 1) migrate
bash "$ROOT/scripts/migrate_local.sh" >/dev/null

# 2) pytest B2 suite + import guard
PYTHONPATH=. python3 -m pytest \
  tests/test_b2l_allowlist_enqueue.py \
  tests/test_b2l_claim_lease.py \
  tests/test_b2l_runner_execute.py \
  tests/test_b2l_worker_loop.py \
  tests/test_b1l_execution_not_migrated.py \
  -q --tb=line

# 3) import guard — no core.harness in package app/
python3 - <<'PY'
import ast
from pathlib import Path
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
PY

# 4) end-to-end: enqueue allowlist + deny sandbox + worker loop drain
python3 - <<'PY'
import json, os
from fastapi.testclient import TestClient
from app.auth import mint_local_token
from app.config import EvalServiceConfig
from app.main import create_app
from app.store.jobs import get_job
from app.worker.loop import run_worker_loop

db = os.environ["AIPLAT_EVAL_DB_URL"]
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
headers = {"Authorization": f"Bearer {mint_local_token(tenant_id='tenant-b2l')}"}

# deny skill
r = client.post("/api/platform/apps/eval/skill-evals/suites/s1/run", headers=headers, json={})
assert r.status_code == 422 and r.json()["error"]["code"] == "sandbox_required", r.text

# enqueue replay
r = client.post(
    "/api/platform/apps/eval/replay/run",
    headers=headers,
    json={
        "idempotency_key": "b2l-closeout-replay",
        "trace": {"ok": True, "steps": [1]},
        "expected": {"ok": True},
    },
)
assert r.status_code == 202, r.text
job_id = r.json()["job_id"]
assert r.json()["process_split_authorized"] is False

hz = client.get("/healthz").json()
assert hz["process_split_authorized"] is False
assert hz.get("b2l_worker_loop") is True
assert hz.get("environment") == "local"

loop = run_worker_loop(
    db,
    worker_id=os.environ["AIPLAT_EVAL_WORKER_ID"],
    idle_sleep_s=0,
    max_jobs=1,
    max_idle_rounds=2,
)
assert loop.processed == 1, loop
assert loop.process_split_authorized is False
stored = get_job(db, job_id)
assert stored and stored["status"] == "succeeded", stored
print(json.dumps({"e2e": "ok", "job_id": job_id, "status": stored["status"]}, ensure_ascii=False))
PY

# 5) authorize posture must stay false
bash "$ROOT/scripts/a3_split_authorize.sh" status | tee "$WORK/authorize_status.txt"
if grep -qiE 'process_split_authorized["[:space:]]*[:=][[:space:]]*true|authorized[[:space:]]*=[[:space:]]*true' "$WORK/authorize_status.txt" 2>/dev/null; then
  echo "REFUSE: authorize flipped true during B2-L closeout" >&2
  exit 1
fi

# 6) evidence JSON
export EVID_DIR STAMP WORK
python3 - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path

stamp = os.environ["STAMP"]
evid = Path(os.environ["EVID_DIR"])
work = Path(os.environ["WORK"])
out = evid / f"local-eval-b2l-closeout-{stamp}.json"
payload = {
    "schema": "eval.b2l.closeout.v0",
    "product_id": "evaluation",
    "phase": "B2-L",
    "environment": "local",
    "process_split_authorized": False,
    "staging_ready": False,
    "accuracy_claim": False,
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "workdir": str(work),
    "checks": {
        "allowlist_enqueue_deny": True,
        "worker_dual_point": True,
        "claim_lease": True,
        "runner_execute_local": True,
        "worker_loop": True,
        "import_guard_no_core_harness": True,
        "e2e_replay_succeeded": True,
        "live_infra_llm": False,
        "note_live_llm": "prompt_eval live provider deferred; local fixture path used for closeout",
    },
    "honesty": "B2-L engineering closeout only — not B3 sandbox, not B4-S/B6 staging authorize",
}
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("wrote", out)
PY

echo "B2-L local closeout PASS (process_split_authorized=false)"
