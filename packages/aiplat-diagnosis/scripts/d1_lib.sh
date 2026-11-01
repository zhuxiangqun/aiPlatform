#!/usr/bin/env bash
# Diagnosis D1 Thin helpers (co-hosted on Central).

d1_repo_pkg() { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; }
d1_repo_root() { cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd; }
d1_aiplat_home() {
  if [[ -n "${AIPLAT_HOME:-}" ]]; then echo "$AIPLAT_HOME"; else echo "${HOME}/.aiplat"; fi
}
d1_prefix() { echo "${AIPLAT_DIAGNOSIS_PREFIX:-$(d1_aiplat_home)/diagnosis}"; }
d1_pkg_version() {
  local pkg; pkg="$(d1_repo_pkg)/package.json"
  python3 -c "import json; print(json.load(open('$pkg')).get('version','0.0.0'))" 2>/dev/null \
    || grep -m1 '"version"' "$pkg" | sed 's/.*: *"\([^"]*\)".*/\1/'
}
d1_require_python() {
  command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found" >&2; return 2; }
}
d1_materialize_version() {
  local dest="$1" src root
  src="$(d1_repo_pkg)"; root="$(d1_repo_root)"
  mkdir -p "$dest"
  for name in scripts contracts package.json README.md docs fixtures; do
    [[ -e "$src/$name" ]] || continue
    rm -rf "$dest/$name"; cp -a "$src/$name" "$dest/$name"
  done
  printf '%s\n' "$root" >"$dest/REPO_ROOT"
  printf '%s\n' "$root/aiPlat-core" >"$dest/CORE_ROOT"
  printf '%s\n' "$root/aiPlat-platform" >"$dest/PLATFORM_ROOT"
}
