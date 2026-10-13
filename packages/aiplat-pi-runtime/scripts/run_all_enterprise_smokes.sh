#!/usr/bin/env bash
# Run all Pi hybrid offline smokes + optional live + factory-in evidence.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
NODE="${NODE:-node}"
PY="${PYTHON:-python3}"

echo "== offline hybrid smokes =="
"$NODE" packages/aiplat-pi-runtime/scripts/enterprise_platform_url_smoke.mjs
"$NODE" packages/aiplat-pi-runtime/scripts/enterprise_kb_smoke.mjs
"$NODE" packages/aiplat-pi-runtime/scripts/enterprise_tools_smoke.mjs
"$NODE" packages/aiplat-pi-runtime/scripts/enterprise_tool_gate_smoke.mjs
"$NODE" packages/aiplat-pi-runtime/scripts/enterprise_memory_smoke.mjs
"$NODE" packages/aiplat-pi-runtime/scripts/enterprise_approval_smoke.mjs

echo "== phase0 offline =="
"$PY" packages/aiplat-pi-runtime/scripts/phase0_offline_check.py

echo "== factory-in evidence (experimental) =="
"$PY" packages/aiplat-pi-runtime/scripts/factory_in_evidence_smoke.py

echo "== hybrid live (SKIP if servers down unless AIPLAT_HYBRID_LIVE=1) =="
"$NODE" packages/aiplat-pi-runtime/scripts/enterprise_hybrid_live_smoke.mjs

echo "AIPLAT_ALL_ENTERPRISE_SMOKES_OK"
