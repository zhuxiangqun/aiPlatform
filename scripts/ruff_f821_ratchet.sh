#!/usr/bin/env bash
# ============================================================================
# ruff_f821_ratchet.sh — F821 ratchet check wrapper
#
# Calls scripts/ruff_f821_ratchet.py for the actual logic.
# ============================================================================
set -euo pipefail
WORKSPACE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE_ROOT"

MODE="${1:---check}"
case "$MODE" in
    --rebuild)  python3 scripts/ruff_f821_ratchet.py --rebuild ;;
    --advisory) python3 scripts/ruff_f821_ratchet.py --advisory ;;
    *)          python3 scripts/ruff_f821_ratchet.py --check ;;
esac
