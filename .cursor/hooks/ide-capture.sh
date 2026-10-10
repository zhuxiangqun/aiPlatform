#!/usr/bin/env bash
# Cursor project hook: stdin JSON → Team Brain (no parallel store).
# Wire in .cursor/hooks.json → sessionEnd / stop.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec python3 "$ROOT/scripts/ide_capture.py" --from-hook "$@"
