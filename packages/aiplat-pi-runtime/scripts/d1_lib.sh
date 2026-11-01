#!/usr/bin/env bash
# Shared helpers for Pi D1 install / upgrade / rollback / backup (Thin only).
# ADR-08 / Gate3: no new update channel; wraps package layout + existing compose/pilot.

d1_repo_pkg() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

d1_repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd
}

d1_aiplat_home() {
  if [[ -n "${AIPLAT_HOME:-}" ]]; then
    echo "$AIPLAT_HOME"
  else
    echo "${HOME}/.aiplat"
  fi
}

# Install prefix: $AIPLAT_HOME/pi  (override with AIPLAT_PI_PREFIX)
d1_prefix() {
  echo "${AIPLAT_PI_PREFIX:-$(d1_aiplat_home)/pi}"
}

d1_pkg_version() {
  local pkg
  pkg="$(d1_repo_pkg)/package.json"
  python3 -c "import json; print(json.load(open('$pkg')).get('version','0.0.0'))" 2>/dev/null \
    || grep -m1 '"version"' "$pkg" | sed 's/.*: *"\([^"]*\)".*/\1/'
}

d1_require_python() {
  command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found" >&2; return 2; }
}

d1_require_node() {
  if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: node not found (need Node >= 22.19)" >&2
    return 2
  fi
  local major
  major="$(node -p "process.versions.node.split('.')[0]" 2>/dev/null || echo 0)"
  if [[ "${major:-0}" -lt 22 ]]; then
    echo "ERROR: Node ${major} < 22.19 required for Pi Thin" >&2
    return 2
  fi
}

# rsync-like copy of Thin runtime essentials into a versioned dir
d1_materialize_version() {
  local dest="$1"
  local src
  src="$(d1_repo_pkg)"
  mkdir -p "$dest"
  for name in bin extensions skills fixtures contracts package.json README.md \
    compose.gate3-pi-thin.yml scripts; do
    if [[ -e "$src/$name" ]]; then
      rm -rf "$dest/$name"
      cp -a "$src/$name" "$dest/$name"
    fi
  done
}
