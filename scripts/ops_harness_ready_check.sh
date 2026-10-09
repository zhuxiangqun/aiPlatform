#!/usr/bin/env bash
# Offline readiness for gold seeds + IDE→Team Brain hooks (no server required).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
fail=0

echo "== gold seeds =="
# Install into ~/.aiplat is best-effort (perms/sandbox); workspace match-only is the gate.
if python3 scripts/eval_code_review_gold.py --install-seeds >/tmp/aiplat_gold_install.txt 2>/tmp/aiplat_gold_install.err; then
  cat /tmp/aiplat_gold_install.txt
else
  echo "WARN: --install-seeds skipped ($(head -n1 /tmp/aiplat_gold_install.err 2>/dev/null || echo permission/env))"
fi
if python3 scripts/eval_code_review_gold.py --match-only \
  --gold-dir aiPlat-core/workspace_seeds/eval/code_review_gold \
  --no-persist --limit 5 --json >/tmp/aiplat_gold_smoke.json; then
  python3 -c "import json;d=json.load(open('/tmp/aiplat_gold_smoke.json'));assert d.get('ok'),d;print('match-only ok cases=',d.get('case_count'),'P=',d.get('precision'),'R=',d.get('recall'))"
else
  echo "FAIL: match-only smoke"; fail=1
fi

echo "== IDE hooks =="
if [[ -f .cursor/hooks.json && -x .cursor/hooks/ide-capture.sh ]]; then
  echo "OK: .cursor/hooks.json + ide-capture.sh"
elif [[ -f .cursor/hooks.json && -f .cursor/hooks/ide-capture.sh ]]; then
  chmod +x .cursor/hooks/ide-capture.sh || true
  echo "OK: hooks present (chmod applied)"
else
  echo "WARN: copy aiPlat-core/workspace_seeds/hooks/ide_capture_hooks.json.example → .cursor/hooks.json"
  fail=1
fi
if [[ -f scripts/ide_capture.py ]]; then
  python3 scripts/ide_capture.py --help >/dev/null
  echo "OK: scripts/ide_capture.py"
else
  echo "FAIL: scripts/ide_capture.py missing"; fail=1
fi

echo "== ontology seeds (offline YAML) =="
# Workspace parse is the gate; install into ~/.aiplat is best-effort (perms/sandbox).
if python3 scripts/check_ontology_seeds_offline.py >/tmp/aiplat_onto_seeds.txt 2>/tmp/aiplat_onto_seeds.err; then
  cat /tmp/aiplat_onto_seeds.txt
  python3 scripts/check_ontology_seeds_offline.py --install >/tmp/aiplat_onto_install.txt 2>/tmp/aiplat_onto_install.err \
    && cat /tmp/aiplat_onto_install.txt \
    || echo "WARN: ontology --install skipped ($(head -n1 /tmp/aiplat_onto_install.err 2>/dev/null || echo permission/env))"
else
  echo "FAIL: ontology workspace seeds invalid"
  cat /tmp/aiplat_onto_seeds.err 2>/dev/null || true
  fail=1
fi

echo "== production knobs (informational) =="
echo "AIPLAT_PROFILE=${AIPLAT_PROFILE:-<(unset, default non-production)}"
echo "Tip: production → OS sandbox fail-closed; set AIPLAT_SANDBOX_FAIL_OPEN=true only for emergency."

exit "$fail"
