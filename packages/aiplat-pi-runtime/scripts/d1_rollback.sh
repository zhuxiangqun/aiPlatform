#!/usr/bin/env bash
# Pi D1 rollback — restore previous runtime symlink; optionally flip bundle.
# Priority matches Gate3: Bundle-first, then runtime (ADR-08 G3-3).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

MODE="runtime"  # runtime | bundle | both
BUNDLE_TARGET=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle)
      MODE="bundle"
      BUNDLE_TARGET="${2:?--bundle requires DIR}"
      shift 2
      ;;
    --both) MODE="both"; shift ;;
    --runtime) MODE="runtime"; shift ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--runtime|--bundle DIR|--both]
  --runtime     flip current → previous version (default)
  --bundle DIR  point bundles/current at DIR (Bundle-first, Gate3 preferred)
  --both        runtime rollback; leave bundles/current
See: reports/five-products/GATE3_PI_THIN_ROLLBACK_DRILL.md
EOF
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 2 ;;
  esac
done

PREFIX="$(d1_prefix)"

rollback_runtime() {
  local prev_file="$PREFIX/.previous_current"
  if [[ ! -f "$prev_file" ]]; then
    echo "ERROR: no $prev_file — run d1_upgrade.sh first or set manually" >&2
    return 4
  fi
  local prev
  prev="$(tr -d '[:space:]' <"$prev_file")"
  if [[ -z "$prev" ]]; then
    echo "ERROR: previous pointer empty" >&2
    return 5
  fi
  if [[ ! -e "$PREFIX/$prev" ]]; then
    echo "ERROR: previous version missing: $PREFIX/$prev" >&2
    return 6
  fi
  local cur
  cur="$(readlink "$PREFIX/current" 2>/dev/null || echo "")"
  echo "$cur" >"$PREFIX/.previous_current"
  ln -sfn "$prev" "$PREFIX/current"
  echo "PASS: runtime rollback current → $prev"
}

rollback_bundle() {
  local target="${1:?}"
  if [[ ! -f "$target/agent_manifest.json" ]]; then
    echo "ERROR: bundle missing agent_manifest.json: $target" >&2
    return 8
  fi
  mkdir -p "$PREFIX/bundles"
  if [[ -L "$PREFIX/bundles/current" || -e "$PREFIX/bundles/current" ]]; then
    readlink "$PREFIX/bundles/current" >"$PREFIX/bundles/.previous" 2>/dev/null || true
  fi
  ln -sfn "$(cd "$target" && pwd)" "$PREFIX/bundles/current"
  if [[ -f "$PREFIX/env" ]] && grep -q '^AIPLAT_APP_HOME=' "$PREFIX/env"; then
    # portable in-place edit
    local tmp
    tmp="$(mktemp)"
    sed "s|^AIPLAT_APP_HOME=.*|AIPLAT_APP_HOME=$PREFIX/bundles/current|" "$PREFIX/env" >"$tmp"
    mv "$tmp" "$PREFIX/env"
  fi
  echo "PASS: bundle rollback → $target"
}

case "$MODE" in
  runtime) rollback_runtime ;;
  bundle) rollback_bundle "$BUNDLE_TARGET" ;;
  both) rollback_runtime; echo "bundles/current unchanged (use --bundle DIR to flip)" ;;
esac

echo "Also: stop process / docker compose -f compose.gate3-pi-thin.yml down if needed"
