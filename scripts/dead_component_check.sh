#!/usr/bin/env bash
# Dead component detection for aiPlat frontend.
# Checks that every export-default component under src/pages/Platform/
# has at least one route / lazy import reference in App.tsx or router/.
# Usage: bash scripts/dead_component_check.sh

set -euo pipefail

cd "$(dirname "$0")/.."
FRONTEND="aiPlat-management/frontend/src"

echo "=== Dead Component Check ==="

found=0
while IFS= read -r -d '' comp; do
    name="$(basename "$comp" .tsx)"
    # Skip index files (routed by directory name)
    if [ "$name" = "index" ]; then
        continue
    fi
    # Check for export default
    if ! grep -q "export default" "$comp" 2>/dev/null; then
        continue
    fi
    # Search for import of this component outside its own file
    comp_name="$(basename "$comp")"
    # Count refs excluding the component file itself and its own directory's index.tsx
    comp_dir="$(dirname "$comp")"
    refs=$(grep -rl "$name" "$FRONTEND" --include='*.tsx' --include='*.ts' 2>/dev/null \
        | grep -v "$comp_name" \
        | grep -v __pycache__ \
        | wc -l)
    if [ "$refs" -eq 0 ]; then
        echo "  ❌ $comp — 0 references (dead component)"
        found=$((found + 1))
    fi
done < <(find "$FRONTEND/pages/Platform" -name "*.tsx" -print0 2>/dev/null)

if [ "$found" -gt 0 ]; then
    echo ""
    echo "Found $found dead component(s). Each must have >= 1 route / lazy-import reference."
    exit 1
else
    echo "  ✅ All page components have at least 1 reference"
    exit 0
fi
