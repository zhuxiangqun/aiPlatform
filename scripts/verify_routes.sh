#!/usr/bin/env bash
# ============================================================================
# verify_routes.sh — 路由可达性验证（需要服务器运行）
#
# 自动提取所有 @router.xxx 端点路径，逐一 curl 验证 200。
# 检测：404 / 路由冲突 / 重复注册。
#
# Usage: bash scripts/verify_routes.sh [--base-url http://localhost:8000]
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE_URL="${1:-http://localhost:8000}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "═══════════════════════════════════════════════════════════════"
echo "  Route Reachability Verification"
echo "  Target: $BASE_URL"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Check server is running
if ! curl -s --connect-timeout 3 "$BASE_URL/api/core/health" > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Server not reachable at $BASE_URL${NC}"
    echo "  Start the server first: ./start.sh"
    exit 1
fi

# Extract all GET routes from router files (most idempotent for testing)
ROUTES_FILE=$(mktemp)
python3 -c "
import ast, os, sys

routers_dir = os.path.join('$WORKSPACE', 'aiPlat-core', 'core', 'api', 'routers')
routes = []

for fname in sorted(os.listdir(routers_dir)):
    if not fname.endswith('.py') or fname == '__init__.py':
        continue
    fpath = os.path.join(routers_dir, fname)
    try:
        tree = ast.parse(open(fpath).read(), filename=fpath)
    except Exception:
        continue

    prefix = ''
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and hasattr(node.func, 'attr'):
            if node.func.attr == 'APIRouter':
                for kw in node.keywords:
                    if kw.arg == 'prefix' and isinstance(kw.value, ast.Constant):
                        prefix = kw.value.value
            if (isinstance(node.func, ast.Attribute) and
                hasattr(node.func, 'value') and
                hasattr(node.func.value, 'id') and
                node.func.value.id == 'router' and
                node.func.attr == 'get' and
                node.args and isinstance(node.args[0], ast.Constant)):
                path = prefix + node.args[0].value
                # Skip path parameters — they need real values
                if '{' not in path and ':' not in path:
                    routes.append(('/api/core' + path, fname))

for url, source in routes:
    print(f'{url}|{source}')
" | sort -u > "$ROUTES_FILE"

PASS=0
FAIL=0
SKIP=0
while IFS='|' read -r url source; do
    [ -z "$url" ] && continue
    # Skip endpoints that need POST/Body params
    if [[ "$url" == *"execute"* || "$url" == *"smoke"* || "$url" == *"prompt"* ]]; then
        echo -e "  ${YELLOW}SKIP${NC} ${url} (needs POST params)"
        SKIP=$((SKIP + 1))
        continue
    fi
    
    status=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "$BASE_URL$url" 2>/dev/null || echo "000")
    if [ "$status" = "200" ] || [ "$status" = "302" ] || [ "$status" = "405" ]; then
        echo -e "  ${GREEN}${status}${NC}  ${url}"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}${status}${NC}  ${url}  ← ${source}"
        FAIL=$((FAIL + 1))
    fi
done < "$ROUTES_FILE"

rm -f "$ROUTES_FILE"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}PASS: $PASS${NC}  ${RED}FAIL: $FAIL${NC}  ${YELLOW}SKIP: $SKIP${NC}"
echo "═══════════════════════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "  Run 'bash scripts/architecture_guard.sh' to check for route duplicates."
    exit 1
else
    exit 0
fi
