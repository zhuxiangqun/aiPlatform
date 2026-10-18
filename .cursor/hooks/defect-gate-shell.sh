#!/usr/bin/env bash
# beforeShellExecution: block gh pr create / git push without a local pass receipt.
# CI unlock is separate (non-author GitHub Approve). stdin: Cursor hook JSON.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VALIDATE="$ROOT/scripts/defect_gate_validate.py"

allow() {
  printf '%s\n' '{"permission":"allow"}'
  exit 0
}

deny() {
  local msg="$1"
  python3 -c '
import json, sys
msg = sys.argv[1]
print(json.dumps({
  "permission": "deny",
  "user_message": msg,
  "agent_message": msg,
}, ensure_ascii=False))
' "$msg"
  exit 0
}

if [[ "${AIPLAT_DEFECT_GATE:-1}" =~ ^(0|false|no|off)$ ]]; then
  allow
fi

if ! command -v python3 >/dev/null 2>&1; then
  deny "defect-gate: python3 required to validate receipt before PR/push"
fi

INPUT="$(cat || true)"
NEED_GATE="$(
  printf '%s' "$INPUT" | python3 -c '
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts"))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "defect_gate_validate", root / "scripts" / "defect_gate_validate.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
try:
    data = json.load(sys.stdin)
except Exception as e:
    print("DETECT_ERROR", e, file=sys.stderr)
    sys.exit(2)
cmd = str(data.get("command") or data.get("cmd") or "")
print("1" if mod.command_needs_gate(cmd) else "0")
' "$ROOT"
)"
DETECT_RC=$?

if [[ "$DETECT_RC" -ne 0 ]]; then
  deny "defect-gate: failed to detect whether command needs a receipt (fail closed)"
fi

if [[ "$NEED_GATE" != "1" ]]; then
  allow
fi

if ! python3 "$VALIDATE" >/tmp/aiplat_defect_gate_hook.out 2>/tmp/aiplat_defect_gate_hook.err; then
  DETAIL="$(head -c 800 /tmp/aiplat_defect_gate_hook.err 2>/dev/null || true)"
  deny "defect-gate blocked this command. Local receipt required for push/PR create. CI still needs non-author Approve. Detail: ${DETAIL}"
fi

allow
