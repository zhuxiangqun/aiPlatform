#!/usr/bin/env bash
# Shared helpers for aiPlat Central D1 Thin (host install layout + smoke).
# No PG/HA process split — packaging only until ADR.

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

# Install prefix: $AIPLAT_HOME/central  (override with AIPLAT_CENTRAL_PREFIX)
d1_prefix() {
  echo "${AIPLAT_CENTRAL_PREFIX:-$(d1_aiplat_home)/central}"
}

d1_pkg_version() {
  local pkg
  pkg="$(d1_repo_pkg)/package.json"
  python3 -c "import json; print(json.load(open('$pkg')).get('version','0.0.0'))" 2>/dev/null \
    || grep -m1 '"version"' "$pkg" | sed 's/.*: *"\([^"]*\)".*/\1/'
}

d1_require_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found" >&2
    return 2
  fi
}

# Materialize Thin host pointers + scripts into a versioned dir
d1_materialize_version() {
  local dest="$1"
  local src root
  src="$(d1_repo_pkg)"
  root="$(d1_repo_root)"
  mkdir -p "$dest"
  for name in scripts contracts package.json README.md docs; do
    if [[ -e "$src/$name" ]]; then
      rm -rf "$dest/$name"
      cp -a "$src/$name" "$dest/$name"
    fi
  done
  # Pointers into monorepo (Thin — no vendored wheel yet)
  printf '%s\n' "$root" >"$dest/REPO_ROOT"
  printf '%s\n' "$root/aiPlat-core" >"$dest/CORE_ROOT"
  printf '%s\n' "$root/aiPlat-platform" >"$dest/PLATFORM_ROOT"
}
