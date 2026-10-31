#!/usr/bin/env bash
# Configure Keycloak realm/client/user for local-staging OIDC (environment=local).
# Does NOT authorize cutover. Does NOT set production_signed.
# Requires: local-staging Keycloak on AIPLAT_LOCAL_KC_URL (default http://127.0.0.1:8081).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
KC_URL="${AIPLAT_LOCAL_KC_URL:-http://127.0.0.1:8081}"
ADMIN_USER="${AIPLAT_LOCAL_KC_ADMIN:-admin}"
ADMIN_PASS="${AIPLAT_LOCAL_KC_ADMIN_PASS:-admin_local_only}"
REALM="${AIPLAT_LOCAL_KC_REALM:-aiplat-local}"
CLIENT_ID="${AIPLAT_LOCAL_KC_CLIENT:-aiplat-local}"
TEST_USER="${AIPLAT_LOCAL_KC_USER:-tenant-admin}"
TEST_PASS="${AIPLAT_LOCAL_KC_USER_PASS:-ChangeMe_local1}"
OUT_DIR="$ROOT/packages/aiplat-central/docs/pg_ha/drills"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_JSON="$OUT_DIR/oidc-local-${STAMP}.json"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

echo "== Keycloak local OIDC setup @ $KC_URL realm=$REALM =="

export AIPLAT_KC_URL="$KC_URL"
export AIPLAT_KC_ADMIN="$ADMIN_USER"
export AIPLAT_KC_ADMIN_PASS="$ADMIN_PASS"
export AIPLAT_KC_REALM="$REALM"
export AIPLAT_KC_CLIENT="$CLIENT_ID"
export AIPLAT_KC_USER="$TEST_USER"
export AIPLAT_KC_USER_PASS="$TEST_PASS"
export AIPLAT_KC_EVIDENCE="$EVIDENCE_JSON"
export AIPLAT_KC_STAMP="$STAMP"

"$PY" - <<'PY'
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

base = os.environ["AIPLAT_KC_URL"].rstrip("/")
admin = os.environ["AIPLAT_KC_ADMIN"]
admin_pass = os.environ["AIPLAT_KC_ADMIN_PASS"]
realm = os.environ["AIPLAT_KC_REALM"]
client_id = os.environ["AIPLAT_KC_CLIENT"]
user = os.environ["AIPLAT_KC_USER"]
user_pass = os.environ["AIPLAT_KC_USER_PASS"]
evidence_path = Path(os.environ["AIPLAT_KC_EVIDENCE"])
stamp = os.environ["AIPLAT_KC_STAMP"]


def http(method: str, url: str, *, data=None, headers=None, expect=(200, 201, 204)):
    body = None
    hdrs = dict(headers or {})
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        else:
            body = data if isinstance(data, bytes) else str(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            code = resp.getcode()
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raw = e.read()
        code = e.code
        ctype = e.headers.get("Content-Type", "") if e.headers else ""
        if code not in expect:
            raise SystemExit(f"HTTP {code} {method} {url}: {raw[:500]!r}") from e
    if code not in expect:
        raise SystemExit(f"unexpected HTTP {code} {method} {url}: {raw[:500]!r}")
    if not raw:
        return code, None
    if "json" in ctype or raw[:1] in (b"{", b"["):
        return code, json.loads(raw.decode("utf-8"))
    return code, raw.decode("utf-8", errors="replace")


# 1) admin token
form = urllib.parse.urlencode(
    {
        "client_id": "admin-cli",
        "username": admin,
        "password": admin_pass,
        "grant_type": "password",
    }
).encode("utf-8")
_, tok = http(
    "POST",
    f"{base}/realms/master/protocol/openid-connect/token",
    data=form,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    expect=(200,),
)
assert isinstance(tok, dict) and tok.get("access_token"), tok
token = tok["access_token"]
auth = {"Authorization": f"Bearer {token}"}

# 2) realm
_, realms = http("GET", f"{base}/admin/realms", headers=auth, expect=(200,))
names = {r.get("realm") for r in (realms or []) if isinstance(r, dict)}
if realm not in names:
    http(
        "POST",
        f"{base}/admin/realms",
        data={"realm": realm, "enabled": True, "registrationAllowed": False},
        headers=auth,
        expect=(201, 204),
    )
    realm_created = True
else:
    realm_created = False

# 3) confidential client with direct access (password grant) for local probe
_, clients = http(
    "GET",
    f"{base}/admin/realms/{urllib.parse.quote(realm)}/clients?clientId={urllib.parse.quote(client_id)}",
    headers=auth,
    expect=(200,),
)
client_uuid = None
client_secret = None
if clients:
    client_uuid = clients[0]["id"]
else:
    http(
        "POST",
        f"{base}/admin/realms/{urllib.parse.quote(realm)}/clients",
        data={
            "clientId": client_id,
            "enabled": True,
            "publicClient": False,
            "secret": "aiplat-local-secret",
            "directAccessGrantsEnabled": True,
            "standardFlowEnabled": True,
            "redirectUris": ["http://127.0.0.1/*", "https://aiplat.local/*"],
            "webOrigins": ["+"],
        },
        headers=auth,
        expect=(201, 204),
    )
    _, clients = http(
        "GET",
        f"{base}/admin/realms/{urllib.parse.quote(realm)}/clients?clientId={urllib.parse.quote(client_id)}",
        headers=auth,
        expect=(200,),
    )
    client_uuid = clients[0]["id"]

_, secret_obj = http(
    "GET",
    f"{base}/admin/realms/{urllib.parse.quote(realm)}/clients/{client_uuid}/client-secret",
    headers=auth,
    expect=(200,),
)
client_secret = (secret_obj or {}).get("value") or "aiplat-local-secret"

# 4) test user + required action CONFIGURE_TOTP (MFA path configured, not production E2E)
_, users = http(
    "GET",
    f"{base}/admin/realms/{urllib.parse.quote(realm)}/users?username={urllib.parse.quote(user)}&exact=true",
    headers=auth,
    expect=(200,),
)
if users:
    user_id = users[0]["id"]
else:
    http(
        "POST",
        f"{base}/admin/realms/{urllib.parse.quote(realm)}/users",
        data={
            "username": user,
            "enabled": True,
            "email": f"{user}@local.test",
            "emailVerified": True,
            "requiredActions": ["CONFIGURE_TOTP"],
        },
        headers=auth,
        expect=(201, 204),
    )
    _, users = http(
        "GET",
        f"{base}/admin/realms/{urllib.parse.quote(realm)}/users?username={urllib.parse.quote(user)}&exact=true",
        headers=auth,
        expect=(200,),
    )
    user_id = users[0]["id"]

http(
    "PUT",
    f"{base}/admin/realms/{urllib.parse.quote(realm)}/users/{user_id}/reset-password",
    data={"type": "password", "value": user_pass, "temporary": False},
    headers=auth,
    expect=(204, 200),
)
# Ensure TOTP configure action remains required (admin MFA path for local)
http(
    "PUT",
    f"{base}/admin/realms/{urllib.parse.quote(realm)}/users/{user_id}",
    data={
        "id": user_id,
        "username": user,
        "enabled": True,
        "email": f"{user}@local.test",
        "requiredActions": ["CONFIGURE_TOTP"],
    },
    headers=auth,
    expect=(204, 200),
)

# 5) discovery + password grant (may fail if TOTP already blocks — record either way)
issuer = f"{base}/realms/{realm}"
_, discovery = http(
    "GET",
    f"{issuer}/.well-known/openid-configuration",
    expect=(200,),
)
assert isinstance(discovery, dict) and discovery.get("issuer") == issuer, discovery

token_form = urllib.parse.urlencode(
    {
        "client_id": client_id,
        "client_secret": client_secret,
        "username": user,
        "password": user_pass,
        "grant_type": "password",
        "scope": "openid",
    }
).encode("utf-8")
token_ok = False
token_note = ""
try:
    code, user_tok = http(
        "POST",
        f"{issuer}/protocol/openid-connect/token",
        data=token_form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        expect=(200, 400, 401),
    )
    if code == 200 and isinstance(user_tok, dict) and user_tok.get("access_token"):
        token_ok = True
        token_note = "password_grant_ok_before_totp_enforcement"
    else:
        token_note = f"password_grant_http_{code}_body={str(user_tok)[:200]}"
except SystemExit as e:
    token_note = str(e)

# Client-credentials-style admin path: admin-cli already proven; also verify realm admin count
_, admin_users = http(
    "GET",
    f"{base}/admin/realms/{urllib.parse.quote(realm)}/users?max=5",
    headers=auth,
    expect=(200,),
)

evidence = {
    "kind": "pg_ha_local_oidc_setup",
    "schema_version": "aiplat.pg_ha.local_oidc.v0",
    "at": stamp,
    "environment": "local",
    "production_signed": False,
    "issuer": issuer,
    "realm": realm,
    "realm_created": realm_created,
    "client_id": client_id,
    "test_user": user,
    "required_actions": ["CONFIGURE_TOTP"],
    "discovery_ok": True,
    "password_grant_ok": token_ok,
    "password_grant_note": token_note,
    "admin_api_users_visible": isinstance(admin_users, list),
    "limitations": [
        "Local Keycloak start-dev only — not HA IdP",
        "CONFIGURE_TOTP required action = MFA path configured; full OTP enrollment UI not automated",
        "Not production tenant MFA / API-key path E2E",
        "Does not authorize cutover",
    ],
    "does_not_authorize_cutover": True,
}
evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("OK wrote", evidence_path)
print("ISSUER", issuer)
print("NOTE: production_signed=false; cutover NOT authorized")
if not token_ok:
    print("NOTE:", token_note)
PY

echo "PASS: pg_ha_local_oidc_setup"
echo "  export AIPLAT_OIDC_ISSUER=${KC_URL}/realms/${REALM}"
