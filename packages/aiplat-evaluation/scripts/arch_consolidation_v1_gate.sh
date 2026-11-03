#!/usr/bin/env bash
# Architecture consolidation v1 freeze gate — ratchet dual-mount + core eval routers.
# NEVER sets process_split_authorized=true.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
cd "$ROOT"

DOC="$ROOT/docs/a3/ARCH_CONSOLIDATION_V1.md"
[[ -f "$DOC" ]] || { echo "REFUSE: missing ARCH_CONSOLIDATION_V1.md" >&2; exit 2; }

EVID_DIR="${AIPLAT_EVAL_ARCH_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

echo "== unit: platform canonical + package composite =="
cd "$REPO"
PYTHONPATH=aiPlat-platform:aiPlat-core python3 -m pytest \
  aiPlat-platform/tests/test_eval_v1_e1_canonical.py -q --tb=line
cd "$ROOT"
PYTHONPATH=. python3 -m pytest tests/test_p1_composite_semantics.py -q --tb=line

python3 - <<PY
import json
import re
from datetime import datetime, timezone
from pathlib import Path

repo = Path("$REPO")
routes = (repo / "aiPlat-platform/api/rest/routes.py").read_text(encoding="utf-8")
# Exactly two mounts of eval_platform_router (canonical + legacy flat).
mounts = len(re.findall(r"include_router\(\s*eval_platform_router", routes))
assert mounts == 2, f"eval_platform_router mounts expected 2, got {mounts}"
assert 'prefix="/api/platform/apps/eval"' in routes
assert "EvalLegacyDeprecationMiddleware" in routes

core_routers = sorted(
    p.name
    for p in (repo / "aiPlat-core/core/api/routers").glob("*eval*")
    if p.suffix == ".py"
)
allowed = {"kb_eval.py", "eval_legacy_shim.py"}
assert set(core_routers) == allowed, f"core eval routers drift: {core_routers}"

# Canonical scoring lives in package
comp = repo / "packages/aiplat-evaluation/app/scoring/composite.py"
assert comp.is_file()
assert "def build_composite" in comp.read_text(encoding="utf-8")

shim = repo / "aiPlat-platform/apps/eval/api/legacy_shim.py"
assert "CANONICAL_PREFIX = \"/api/platform/apps/eval\"" in shim.read_text(encoding="utf-8")

# v1.1b: platform eval API must not import/use sqlite3 (ops live in core service).
api_dir = repo / "aiPlat-platform/apps/eval/api"
sqlite_files = sorted(
    p.name
    for p in api_dir.glob("*.py")
    if "sqlite3" in p.read_text(encoding="utf-8")
)
assert sqlite_files == [], f"platform eval sqlite3 drift: {sqlite_files}"
kb_eval_plat = (api_dir / "kb_eval.py").read_text(encoding="utf-8")
assert "kb_eval_list_samples" in kb_eval_plat
prompt_plat = (api_dir / "prompt_eval.py").read_text(encoding="utf-8")
assert "prompt_eval_list_test_cases" in prompt_plat
assert "get_db_connection" not in prompt_plat

evid = Path("$EVID_DIR")
stamp = "$STAMP"
payload = {
    "schema": "eval.arch.consolidation_gate.v1",
    "product_id": "evaluation",
    "environment": "local",
    "process_split_authorized": False,
    "accuracy_claim": False,
    "canonical_prefix": "/api/platform/apps/eval",
    "eval_platform_router_mounts": mounts,
    "core_eval_router_files": core_routers,
    "freeze": {
        "max_eval_platform_router_mounts": 2,
        "allowed_core_eval_routers": sorted(allowed),
    },
    "platform_sqlite_files": sqlite_files,
    "remaining_gaps": [
        "legacy_flat_mount_still_present",
        "platform_runs_skill_still_thick",
        "central_legacy_7dim_dual_path",
        "product_root_incomplete",
    ],
    "honesty": (
        "v1 freeze + v1.1 kb_eval/prompt_eval thinned; dual mount==2; "
        "platform eval sqlite3 cleared; "
        "package build_composite remains engineering canonical; not authorize"
    ),
    "recorded_at": stamp or datetime.now(timezone.utc).isoformat(),
}
path = evid / f"local-eval-arch-consolidation-v1-{stamp}.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"gate": "ok", "evidence": str(path), "mounts": mounts, "accuracy_claim": False}, ensure_ascii=False))
PY

bash "$ROOT/scripts/a3_split_authorize.sh" status >/dev/null
echo "arch consolidation v1 gate PASS (freeze; authorize=false)"
