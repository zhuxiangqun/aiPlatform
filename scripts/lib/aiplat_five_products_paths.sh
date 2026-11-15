#!/usr/bin/env bash
# Five-products ops evidence path — single SoT for shell scripts.
# Override: AIPLAT_FIVE_PRODUCTS_OPS_REL=reports/.../ops
#
# Usage (after ROOT is known):
#   # shellcheck source=lib/aiplat_five_products_paths.sh
#   source "$ROOT/scripts/lib/aiplat_five_products_paths.sh"
#   OPS="$(aiplat_five_products_ops "$ROOT")"

AIPLAT_FIVE_PRODUCTS_OPS_REL="${AIPLAT_FIVE_PRODUCTS_OPS_REL:-reports/products/five-products/ops}"

aiplat_five_products_ops() {
  local root="${1:?aiplat_five_products_ops: repo root required}"
  printf '%s\n' "${root%/}/${AIPLAT_FIVE_PRODUCTS_OPS_REL}"
}
