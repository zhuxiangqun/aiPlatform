#!/usr/bin/env bash
# validate|sign a live-*.json — does not authorize; never touches checklist.
# sign refuses unless all items.done + non-empty evidence; refuses scaffold env by default.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CMD="${1:-}"
FILE="${2:-}"
ALLOW_SCAFFOLD=0
[[ "${3:-}" == "--allow-scaffold-env" ]] && ALLOW_SCAFFOLD=1

usage() {
  echo "usage: ops_live_sign.sh validate <live.json>" >&2
  echo "       ops_live_sign.sh sign <live.json> [--allow-scaffold-env]" >&2
  exit 2
}
[[ -n "$CMD" && -n "$FILE" ]] || usage
[[ -f "$FILE" ]] || { echo "FAIL: not a file: $FILE" >&2; exit 2; }

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
export AIPLAT_LIVE_SIGN_CMD="$CMD"
export AIPLAT_LIVE_SIGN_FILE="$(cd "$(dirname "$FILE")" && pwd)/$(basename "$FILE")"
export AIPLAT_LIVE_ALLOW_SCAFFOLD="$ALLOW_SCAFFOLD"

"$PY" - <<'PY'
from __future__ import annotations
import json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts/lib").resolve()))
from aiplat_live_sign import sign_live_file, validate_live_file

cmd = os.environ["AIPLAT_LIVE_SIGN_CMD"]
path = Path(os.environ["AIPLAT_LIVE_SIGN_FILE"])
allow = os.environ.get("AIPLAT_LIVE_ALLOW_SCAFFOLD") == "1"

if cmd == "validate":
    report = validate_live_file(path)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["items_complete"] and not report["scaffoldish_environment"] else 1)

if cmd == "sign":
    report = sign_live_file(path, allow_scaffold_env=allow)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report.get("signed"):
        print(
            f"REFUSED: ops_live_sign — {report.get('refused')} "
            f"(missing={report.get('missing_or_incomplete_items')})",
            file=sys.stderr,
        )
        sys.exit(1)
    print("OK signed production_signed=true (checklist/authorize untouched)", file=sys.stderr)
    sys.exit(0)

print("usage: validate|sign", file=sys.stderr)
sys.exit(2)
PY
