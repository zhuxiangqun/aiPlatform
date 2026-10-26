#!/usr/bin/env bash
# ADR-09 Pi Thin optional-deploy entry name (alias).
# Behavior identical to gate3_pi_thin_pilot.sh — no long-running compose.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec bash "$ROOT/gate3_pi_thin_pilot.sh" "$@"
