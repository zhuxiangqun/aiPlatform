#!/usr/bin/env bash
# Temp-dir regression for ops_live_sign — does not touch package drills.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/aiplat-live-sign.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

cat >"$TMP/live-incomplete.json" <<'EOF'
{
  "kind": "pg_ha_live_drill_evidence",
  "drill_id": "t-incomplete",
  "environment": "staging",
  "production_signed": false,
  "items": {
    "oidc_full": {"done": false, "evidence": ""},
    "pg_migration": {"done": true, "evidence": "ok"}
  }
}
EOF

cat >"$TMP/live-complete.json" <<'EOF'
{
  "kind": "pg_ha_live_drill_evidence",
  "drill_id": "t-complete",
  "environment": "staging",
  "production_signed": false,
  "items": {
    "oidc_full": {"done": true, "evidence": "mfa+login log"},
    "pg_migration": {"done": true, "evidence": "rowcount match"}
  }
}
EOF

cat >"$TMP/live-scaffold-env.json" <<'EOF'
{
  "kind": "pg_ha_live_drill_evidence",
  "drill_id": "t-scaffold",
  "environment": "scaffold",
  "production_signed": false,
  "items": {
    "oidc_full": {"done": true, "evidence": "x"}
  }
}
EOF

echo "== incomplete → validate fail / sign refuse =="
set +e
bash scripts/ops_live_sign.sh validate "$TMP/live-incomplete.json"
v1=$?
bash scripts/ops_live_sign.sh sign "$TMP/live-incomplete.json"
s1=$?
set -e
[[ "$v1" -ne 0 && "$s1" -ne 0 ]] || exit 1
python3 -c "import json; assert json.load(open('$TMP/live-incomplete.json'))['production_signed'] is False"

echo "== complete → sign ok =="
bash scripts/ops_live_sign.sh sign "$TMP/live-complete.json"
python3 -c "import json; assert json.load(open('$TMP/live-complete.json'))['production_signed'] is True"

echo "== scaffold env → sign refuse =="
set +e
bash scripts/ops_live_sign.sh sign "$TMP/live-scaffold-env.json"
s2=$?
set -e
[[ "$s2" -ne 0 ]] || exit 1

# package scaffold must refuse
set +e
bash scripts/ops_live_sign.sh sign packages/aiplat-central/docs/pg_ha/drills/live-scaffold-pgha-20261031.json
s3=$?
set -e
[[ "$s3" -ne 0 ]] || exit 1
python3 -c "import json; assert json.load(open('packages/aiplat-central/docs/pg_ha/drills/live-scaffold-pgha-20261031.json'))['production_signed'] is False"

echo "PASS: test_ops_live_sign"
