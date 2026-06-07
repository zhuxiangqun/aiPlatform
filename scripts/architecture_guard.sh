#!/usr/bin/env bash
# ============================================================================
# architecture_guard.sh — architecture compliance checker (delegates to Python)
#
# Rules are now defined in:
#   aiPlat-core/core/management/arch_guard_rules.yaml     (declarative, ~40 grep rules)
#   aiPlat-core/core/management/arch_guard_rules/*.py     (complex checks)
#   scripts/guard_frontend.py                              (frontend proxy + API contract)
#
# Add a new rule:
#   Simple: add 6 lines to arch_guard_rules.yaml
#   Complex: add a class to arch_guard_rules/
#   Frontend: add checks to guard_frontend.py
# ============================================================================

set -euo
WORKSPACE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE_ROOT"

python3 scripts/architecture_guard.py "$@"
python3 aiPlat-core/core/management/capability_convergence.py "$@" --force
python3 scripts/guard_frontend.py
