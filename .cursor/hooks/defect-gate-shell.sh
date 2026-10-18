#!/usr/bin/env bash
# beforeShellExecution: block gh pr create / protected push without a pass receipt.
# stdin: Cursor hook JSON. stdout: permission JSON.
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
import json, re, sys
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
cmd = str(data.get("command") or data.get("cmd") or "")
# Commit messages and heredocs must not look like a push/PR command.
cmd = re.sub(r"<<-?\s*'\''?\\?EOF'\''?.*?^EOF", " ", cmd, flags=re.S | re.M)
cmd = re.sub(r"'\''(?:\\.|[^'\''])*'\''", " ", cmd, flags=re.S)
cmd = re.sub(r"\"(?:\\.|[^\"])*\"", " ", cmd, flags=re.S)
gate = bool(re.search(r"(?:^|[;&|\s])gh\s+pr\s+create(?:\s|$)", cmd))
gate = gate or bool(re.search(r"(?:^|[;&|\s])git\s+push(?:\s|$)", cmd))
print("1" if gate else "0")
' 2>/dev/null || echo 0
)"

if [[ "$NEED_GATE" != "1" ]]; then
  allow
fi

if ! python3 "$VALIDATE" >/tmp/aiplat_defect_gate_hook.out 2>/tmp/aiplat_defect_gate_hook.err; then
  DETAIL="$(head -c 800 /tmp/aiplat_defect_gate_hook.err 2>/dev/null || true)"
  deny "defect-gate blocked this command. Run the defect-gate skill, write .aiplat/defect_gate/receipt.json with status=pass for current HEAD, then: python3 scripts/defect_gate_validate.py. Detail: ${DETAIL}"
fi

allow
