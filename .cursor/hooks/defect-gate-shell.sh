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
  if command -v python3 >/dev/null 2>&1; then
    python3 -c '
import json, sys
msg = sys.argv[1]
print(json.dumps({
  "permission": "deny",
  "user_message": msg,
  "agent_message": msg,
}, ensure_ascii=False))
' "$msg"
  else
    printf '%s\n' "{\"permission\":\"deny\",\"user_message\":$(printf '%s' "$msg" | sed 's/"/\\"/g'),\"agent_message\":\"$msg\"}"
  fi
  exit 0
}

if [[ "${AIPLAT_DEFECT_GATE:-1}" =~ ^(0|false|no|off)$ ]]; then
  allow
fi

INPUT="$(cat || true)"

# Fast path (bash only): non-push / non-pr-create Shell must return allow
# immediately. A slow Python detect was being canceled and fail-closed the
# whole session, blocking even `git status`.
CMD="$(printf '%s' "$INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
if [[ -z "$CMD" ]]; then
  CMD="$(printf '%s' "$INPUT" | sed -n "s/.*\"cmd\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -1)"
fi
# Unescape common JSON sequences for matching.
CMD_FLAT="$(printf '%s' "$CMD" | sed 's/\\n/\n/g; s/\\"/"/g')"
# Drop heredoc bodies so commit messages mentioning "git push" do not match.
CMD_FLAT="$(printf '%s' "$CMD_FLAT" | awk '
  BEGIN { skip=0 }
  /^[[:space:]]*cat[[:space:]]+<<'\''?EOF'\''?/ { skip=1; next }
  /^EOF$/ { skip=0; next }
  !skip { print }
')"

if ! printf '%s' "$CMD_FLAT" | grep -qE '(^|[;&|[:space:]])gh[[:space:]]+pr[[:space:]]+create([[:space:]]|$)' \
  && ! printf '%s' "$CMD_FLAT" | grep -qE '(^|[;&|[:space:]])git[[:space:]]+push([[:space:]]|$)'; then
  allow
fi

if ! command -v python3 >/dev/null 2>&1; then
  deny "defect-gate: python3 required to validate receipt before PR/push"
fi

if ! python3 "$VALIDATE" >/tmp/aiplat_defect_gate_hook.out 2>/tmp/aiplat_defect_gate_hook.err; then
  DETAIL="$(head -c 800 /tmp/aiplat_defect_gate_hook.err 2>/dev/null || true)"
  deny "defect-gate blocked this command. Local receipt required for push/PR create. CI still needs non-author Approve. Detail: ${DETAIL}"
fi

allow
