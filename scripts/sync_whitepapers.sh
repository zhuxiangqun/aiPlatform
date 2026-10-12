#!/usr/bin/env bash
# sync_whitepapers.sh — regenerate status whitepaper + five volumes, then freshness check
# Truth chain: CAPABILITIES / assessment-scores / suite → generated whitepapers
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== sync_whitepapers: generate =="
python3 scripts/generate_platform_whitepaper.py
python3 scripts/generate_whitepaper_volumes.py

echo "== sync_whitepapers: check =="
python3 scripts/generate_platform_whitepaper.py --check
python3 scripts/generate_whitepaper_volumes.py --check

echo "OK: whitepapers synced"
