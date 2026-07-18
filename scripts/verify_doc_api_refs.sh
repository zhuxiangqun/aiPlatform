#!/bin/bash
# verify_doc_api_refs.sh — 检测 docs/manuals/ 中过期的 API 路径引用
#
# 提取文档中所有 `GET /xxx`、`POST /xxx` 等 API 引用，
# 与实际 FastAPI 注册的路由交叉验证，发现不匹配。
#
# 用法:
#   bash scripts/verify_doc_api_refs.sh            # 全量检查
#   bash scripts/verify_doc_api_refs.sh --dry-run  # 仅报告，不修复
#   bash scripts/verify_doc_api_refs.sh --fix      # 标记过期引用

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
DRY_RUN=false
FIX=false

if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=true; fi
if [ "${1:-}" = "--fix" ]; then FIX=true; fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  VERIFY DOC API REFS — 文档中 API 引用 vs 实际注册路由"
echo "═══════════════════════════════════════════════════════════════"

STALE=0
TOTAL=0
TMPFILE=$(mktemp)

# Step 1: Collect all registered FastAPI routes from Python AST
python3 - "$WORKSPACE" > "$TMPFILE" << 'PYEOF'
import sys, os, ast, re

workspace = sys.argv[1]
routes = set()

def extract_routes(root_dir, prefix=""):
    if not os.path.isdir(root_dir):
        return
    for dirpath, _, filenames in os.walk(root_dir):
        if '__pycache__' in dirpath or 'node_modules' in dirpath:
            continue
        for fname in filenames:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath) as f:
                    tree = ast.parse(f.read())
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # @router.get("/path") or app.get("/path") or APIRouter(prefix="/x")
                    func = None
                    if isinstance(node.func, ast.Attribute):
                        func = node.func.attr
                    elif isinstance(node.func, ast.Name):
                        func = node.func.id
                    if func in ('get', 'post', 'put', 'delete', 'patch') and node.args:
                        arg = node.args[0]
                        if isinstance(arg, ast.Constant):
                            path = str(arg.value)
                            if path.startswith('/'):
                                routes.add(f"{func.upper()} {path}")
                    # APIRouter(prefix="/x")
                    if isinstance(node.func, ast.Name) and node.func.id == 'APIRouter':
                        for kw in node.keywords:
                            if kw.arg == 'prefix' and isinstance(kw.value, ast.Constant):
                                prefix = str(kw.value.value)

    # Also collect from apps.yaml API prefixes
    apps_yaml = os.path.join(workspace, 'aiPlat-platform/registry/apps.yaml')
    if os.path.exists(apps_yaml):
        import yaml
        with open(apps_yaml) as f:
            reg = yaml.safe_load(f) or {}
        for mod in reg.get('modules', {}).values():
            pref = mod.get('api_prefix', '')
            if pref:
                routes.add(f"PREFIX {pref}")

for root in [
    'aiPlat-core/core/api/routers',
    'aiPlat-platform/apps',
    'aiPlat-core/core/api',
]:
    full = os.path.join(workspace, root)
    extract_routes(full)

for r in sorted(routes):
    print(r)
PYEOF

REGISTERED_COUNT=$(wc -l < "$TMPFILE")
echo "  Registered routes found: $REGISTERED_COUNT"

# Step 2: Scan docs/manuals/ for API path references (Python for correctness)
echo ""
echo "━━━ Scanning docs/manuals/ for API references ━━━"

STALE=0
TOTAL=0
STALE_LIST=$(mktemp)

python3 - "$WORKSPACE" "$TMPFILE" > "$STALE_LIST" << 'PYEOF'
import sys, os, re

workspace = sys.argv[1]
routes_file = sys.argv[2]

# Load registered routes + prefixes
registered = set()
prefixes = set()
with open(routes_file) as f:
    for line in f:
        line = line.strip()
        if line.startswith("PREFIX "):
            prefixes.add(line[7:])
        else:
            registered.add(line)

# Scan docs
doc_dir = os.path.join(workspace, "docs/manuals")
total = 0
stale = 0

for dirpath, _, filenames in os.walk(doc_dir):
    for fname in filenames:
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(dirpath, fname)
        rel = os.path.relpath(fpath, workspace)
        try:
            with open(fpath) as f:
                lines = f.readlines()
        except Exception:
            continue

        for lineno, line in enumerate(lines, 1):
            # Pattern 1: `METHOD /path`
            for m in re.finditer(r'`(GET|POST|PUT|DELETE|PATCH) (/[^`]+)`', line):
                method = m.group(1)
                path = m.group(2).split("?")[0]
                total += 1
                entry = f"{method} {path}"
                if entry not in registered:
                    # Check prefix match
                    matched = any(path.startswith(p) for p in prefixes)
                    if not matched:
                        stale += 1
                        print(f"⚠️  {rel}:{lineno} → {entry}")

            # Pattern 2: bare METHOD /path (no backticks, not inside URLs)
            for m in re.finditer(r'\b(GET|POST|PUT|DELETE|PATCH) (/[a-zA-Z0-9/_{}-]+)\b', line):
                method = m.group(1)
                path = m.group(2)
                if "http" in line[m.start()-5:m.start()]:  # skip URLs
                    continue
                if path.startswith("/api/") and any(path.startswith(p) for p in prefixes):
                    continue  # matched by prefix
                total += 1
                entry = f"{method} {path}"
                if entry not in registered:
                    matched = any(path.startswith(p) or path.startswith("/api/core" + p) 
                                  for p in prefixes)
                    if not matched:
                        stale += 1
                        print(f"⚠️  {rel}:{lineno} → {entry}")

print(f"__TOTAL__ {total}")
print(f"__STALE__ {stale}")
PYEOF

# Parse results
while IFS= read -r line; do
    if [[ "$line" == __TOTAL__* ]]; then
        TOTAL=$(echo "$line" | awk '{print $2}')
    elif [[ "$line" == __STALE__* ]]; then
        STALE=$(echo "$line" | awk '{print $2}')
    elif [[ "$line" == ⚠️* ]]; then
        echo "  $line"
    fi
done < "$STALE_LIST"

rm -f "$TMPFILE" "$STALE_LIST"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Results: $STALE stale out of $TOTAL total API references"
if [ "$STALE" -gt 0 ]; then
    echo ""
    echo "  ⚠️  $STALE stale API reference(s) found."
    echo "  Run with --fix to auto-mark stale references."
    echo "  Then manually review and replace with correct endpoints."
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    exit 1
else
    echo "  ✅ All API references match registered routes."
    echo "═══════════════════════════════════════════════════════════════"
    exit 0
fi
