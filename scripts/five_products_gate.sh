#!/usr/bin/env bash
# Five-products local gate — version + compat + security + contract validators + unit adapters.
# Does NOT Accept ADRs. Does NOT start long-running services.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

echo "== STATUS↔manifest sync =="
"$PY" scripts/check_five_products_status_sync.py

echo "== Packaging surface (shared D1/D2 base) =="
bash scripts/check_five_products_packaging_surface.sh

echo "== A2 version =="
bash packages/aiplat-central/scripts/a2_version_check.sh

echo "== D2 compat =="
bash packages/aiplat-central/scripts/d2_compat_check.sh

echo "== D2+ security =="
bash packages/aiplat-central/scripts/d2_security_check.sh

echo "== aiPlat Central D2 Thin scope =="
test -f packages/aiplat-central/docs/D2_THIN.md
test -x packages/aiplat-central/scripts/d2_local_closeout.sh
grep -q 'Never sets cutover_authorized=true' packages/aiplat-central/scripts/d2_local_closeout.sh

echo "== Pi D2 admin/security pack =="
bash packages/aiplat-pi-runtime/scripts/d2_admin_check.sh

echo "== Pi D3 local closeout (bundle/SOC/N-1; not production) =="
bash packages/aiplat-pi-runtime/scripts/d3_local_closeout.sh

echo "== Module contract samples =="
python3 reports/five-products/modules/ontology/contracts/validate_sample.py
python3 reports/five-products/modules/evaluation/contracts/validate_sample.py
python3 reports/five-products/modules/aiplat/contracts/validate_sample.py
python3 reports/five-products/modules/fde/contracts/validate_sample.py

echo "== Unit adapters =="
"$PY" -m pytest \
  aiPlat-core/core/tests/unit/test_capability_version.py \
  aiPlat-core/core/tests/unit/test_control_plane_v0.py \
  aiPlat-core/core/tests/unit/test_ontology_api_v0.py \
  aiPlat-core/core/tests/unit/test_eval_protocol_v0.py \
  -q --tb=line

echo "== Ontology D1 smoke =="
bash packages/aiplat-ontology/scripts/d1_smoke.sh

echo "== Ontology D2 cohost admin pack =="
bash packages/aiplat-ontology/scripts/d2_admin_check.sh

echo "== Evaluation D1 smoke =="
bash packages/aiplat-evaluation/scripts/d1_smoke.sh

echo "== Evaluation D2 cohost admin pack =="
bash packages/aiplat-evaluation/scripts/d2_admin_check.sh

echo "== FDE Field D1 smoke =="
bash packages/aiplat-fde/scripts/d1_smoke.sh

echo "== FDE Field D2 admin/security pack =="
bash packages/aiplat-fde/scripts/d2_admin_check.sh

echo "== Ontology A3 local rehearsal (file dual-write/rollback; not live) =="
bash packages/aiplat-ontology/scripts/a3_local_rehearsal.sh

echo "== Evaluation A3 local rehearsal (SQLite backup/rollback; not live) =="
bash packages/aiplat-evaluation/scripts/a3_local_rehearsal.sh

echo "== Ontology A3 prep (split stays unauthorized; ADR Accepted conditional) =="
bash packages/aiplat-ontology/scripts/a3_prep_check.sh

echo "== Evaluation A3 prep (split stays unauthorized; ADR Accepted conditional) =="
bash packages/aiplat-evaluation/scripts/a3_prep_check.sh

echo "== PG/HA local rehearsal (SQLite; optional DSN/docker PG) =="
bash packages/aiplat-central/scripts/pg_ha_local_rehearsal.sh

echo "== PG/HA HA failover rehearsal (docker ephemeral; not production) =="
bash packages/aiplat-central/scripts/pg_ha_ha_failover_rehearsal.sh

echo "== PG/HA prep check (cutover stays unauthorized) =="
bash packages/aiplat-central/scripts/pg_ha_prep_check.sh

echo "== Authorize hard gates (expect REFUSE while checklist has 🟨) =="
bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh status
bash packages/aiplat-ontology/scripts/a3_split_authorize.sh status
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh status
if bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh authorize; then
  echo "FAIL: cutover authorize must REFUSE while not all ✅" >&2
  exit 1
fi
if bash packages/aiplat-ontology/scripts/a3_split_authorize.sh authorize; then
  echo "FAIL: ontology split authorize must REFUSE while not all ✅" >&2
  exit 1
fi
if bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh authorize; then
  echo "FAIL: evaluation split authorize must REFUSE while not all ✅" >&2
  exit 1
fi
bash packages/aiplat-pi-runtime/scripts/d3_authorize.sh status
if bash packages/aiplat-pi-runtime/scripts/d3_authorize.sh authorize; then
  echo "FAIL: pi d3 authorize must REFUSE while not all ✅" >&2
  exit 1
fi
echo "OK authorize gates REFUSED (expected)"

echo "== Ops live status (read-only aggregate) =="
bash scripts/ops_live_status.sh

echo "== Ops live refuse proof (signed-live helper; no authorize) =="
bash scripts/ops_live_refuse_proof.sh

echo "== Live evidence authorize gate regression (temp dirs; may authorize temp only) =="
bash scripts/test_live_evidence_authorize_gate.sh

echo "== Ops live sign gate regression (temp dirs; package scaffold stays unsigned) =="
bash scripts/test_ops_live_sign.sh

echo "PASS: five_products_gate"
echo "NOTE: Field · PG/HA · Ontology A3 · Evaluation A3 · Pi D3 Accepted(conditional)."
echo "NOTE: cutover/process_split/d3_production unauthorized until checklists all ✅."
echo "See reports/five-products/STATUS.md · OPS_LIVE_RUNBOOK.md"
