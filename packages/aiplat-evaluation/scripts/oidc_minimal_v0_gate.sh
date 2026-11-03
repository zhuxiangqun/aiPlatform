#!/usr/bin/env bash
# OIDC minimal v0 — local JWT path + Keycloak compose profile (≠ enterprise realm).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DOC="$ROOT/docs/a3/OIDC_MINIMAL_V0.md"
COMPOSE="$ROOT/compose/docker-compose.b4s-local.yml"
EVID_DIR="${AIPLAT_EVAL_OIDC_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LIVE="${AIPLAT_EVAL_OIDC_LIVE:-0}"

[[ -f "$DOC" && -f "$COMPOSE" ]] || {
  echo "REFUSE: missing OIDC doc or b4s compose" >&2
  exit 2
}

python3 - <<PY
import json
from pathlib import Path

doc = Path("$DOC").read_text(encoding="utf-8")
assert "AIPLAT_EVAL_REQUIRE_AUTH" in doc or "A6" in doc
assert "keycloak" in doc.lower()
compose = Path("$COMPOSE").read_text(encoding="utf-8")
assert "keycloak:" in compose
assert 'profiles: ["keycloak"]' in compose or "profiles: [\"keycloak\"]" in compose
a_close = Path("$ROOT/docs/a3/A_LOCAL_CLOSEOUT.md").read_text(encoding="utf-8")
assert "OIDC" in a_close or "JWT" in a_close

jwks_ok = None
if "$LIVE" == "1":
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:8088/realms/master/protocol/openid-connect/certs", timeout=3) as r:
            jwks_ok = r.status == 200
    except Exception:
        jwks_ok = False

payload = {
    "schema": "eval.oidc_minimal.gate.v0",
    "product_id": "evaluation",
    "environment": "local",
    "enterprise_realm": False,
    "process_split_authorized": False,
    "accuracy_claim": False,
    "paths": ["A6_local_jwt", "b4s_keycloak_profile"],
    "keycloak_compose_profile": True,
    "jwks_live_probed": "$LIVE" == "1",
    "jwks_ok": jwks_ok,
    "doc": "docs/a3/OIDC_MINIMAL_V0.md",
    "recorded_at": "$STAMP",
    "honesty": "minimal local OIDC/tenant path only; not enterprise realm; not staging",
}
path = Path("$EVID_DIR") / f"local-eval-oidc-minimal-v0-$STAMP.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"gate": "ok", "evidence": str(path), "enterprise_realm": False}, ensure_ascii=False))
PY

echo "oidc minimal v0 gate PASS (not enterprise realm; authorize=false)"
