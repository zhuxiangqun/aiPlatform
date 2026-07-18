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
# Step 1: Collect all registered FastAPI routes from Python AST + apps.yaml prefixes

python3 - "$WORKSPACE" > "$TMPFILE" << 'PYEOF'
import sys, os, ast, re, yaml

workspace = sys.argv[1]
routes = set()

# ── 1a: Load apps.yaml module → prefix mapping ──
module_prefixes = {}
apps_yaml = os.path.join(workspace, 'aiPlat-platform/registry/apps.yaml')
if os.path.exists(apps_yaml):
    with open(apps_yaml) as f:
        reg = yaml.safe_load(f) or {}
    for mod in reg.get('modules', {}).values():
        pref = mod.get('api_prefix', '')
        api_mod = mod.get('api_module', '')
        if pref and api_mod:
            # e.g., "apps.fde.api.router" → "fde"
            mod_dir = api_mod.replace('.', '/').replace('/router', '').replace('/api', '')
            module_prefixes[mod_dir] = pref
            routes.add(f"PREFIX {pref}")

# ── 1b: Collect core routers (aiPlat-core/core/api/routers/) ──
def extract_from_dir(root_dir):
    if not os.path.isdir(root_dir):
        return
    # First pass: find the parent router prefix from router.py (if exists)
    dir_prefix = ""
    router_py = os.path.join(root_dir, "router.py")
    if os.path.exists(router_py):
        try:
            with open(router_py) as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    if isinstance(node.value, ast.Call):
                        func_name = ""
                        if hasattr(node.value.func, 'id'):
                            func_name = node.value.func.id
                        elif hasattr(node.value.func, 'attr'):
                            func_name = node.value.func.attr
                        if func_name == 'APIRouter':
                            for kw in node.value.keywords:
                                if kw.arg == 'prefix' and isinstance(kw.value, ast.Constant):
                                    dir_prefix = str(kw.value.value)
        except Exception:
            pass

    # Second pass: collect routes from all .py files
    for dirpath, _, filenames in os.walk(root_dir):
        if '__pycache__' in dirpath:
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
            # Check for file-specific APIRouter prefix (overrides dir prefix)
            file_prefix = dir_prefix
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    if isinstance(node.value, ast.Call):
                        func_name = ""
                        if hasattr(node.value.func, 'id'):
                            func_name = node.value.func.id
                        elif hasattr(node.value.func, 'attr'):
                            func_name = node.value.func.attr
                        if func_name == 'APIRouter':
                            for kw in node.value.keywords:
                                if kw.arg == 'prefix' and isinstance(kw.value, ast.Constant):
                                    file_prefix = str(kw.value.value)
            # Extract route decorators
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    func = node.func.attr
                    if func in ('get', 'post', 'put', 'delete', 'patch') and node.args:
                        arg = node.args[0]
                        if isinstance(arg, ast.Constant):
                            path = str(arg.value)
                            if path.startswith('/'):
                                full = file_prefix + path if file_prefix else path
                                routes.add(f"{func.upper()} {full}")

# ── 1c: Collect platform app routes with prefix resolution ──
for mod_dir in ['apps/fde/api', 'apps/workbench/api', 'apps/value/api',
                 'apps/learning/api', 'apps/prompt/api', 'apps/eval/api',
                 'apps/misc/api', 'apps/ontology_editor/api']:
    full_dir = os.path.join(workspace, 'aiPlat-platform', mod_dir)
    if not os.path.isdir(full_dir):
        continue
    # Get prefix from module_prefixes by matching directory
    prefix = ""
    for key, val in module_prefixes.items():
        if mod_dir.startswith(key):
            prefix = val
            break
    extract_from_dir(full_dir)

# ── 1d: Collect core routers ──
extract_from_dir(os.path.join(workspace, 'aiPlat-core/core/api/routers'))
extract_from_dir(os.path.join(workspace, 'aiPlat-core/core/api'))

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
full_routes = {}  # method -> set of paths
with open(routes_file) as f:
    for line in f:
        line = line.strip()
        if line.startswith("PREFIX "):
            prefixes.add(line[7:])
        else:
            registered.add(line)
            parts = line.split(" ", 1)
            if len(parts) == 2:
                method, rpath = parts
                full_routes.setdefault(method, set()).add(rpath)

def normalize_path(path):
    """Normalize path parameters: /{session_id} → /{param} for comparison."""
    return re.sub(r'/\{[^}]+\}', '/{param}', path)

def match_route(method, path):
    """Check if a doc-referenced route matches any registered route.
    Uses exact match first, then normalized path matching.
    """
    entry = f"{method} {path}"
    if entry in registered:
        return True
    # Normalized match: handle parameter name differences (/fde/sessions/{id} vs /fde/sessions/{session_id})
    norm_path = normalize_path(path)
    norm_entry = f"{method} {norm_path}"
    registered_paths = full_routes.get(method, set())
    for rpath in registered_paths:
        if normalize_path(rpath) == norm_path:
            return True
        # Bidirectional suffix: doc path ends with registered path OR vice versa
        if normalize_path(rpath).endswith(norm_path) or norm_path.endswith(normalize_path(rpath)):
            return True
        if rpath.endswith(path) or path.endswith(rpath):
            return True
    # Check prefixes from apps.yaml
    for p in prefixes:
        if path.startswith(p) or path.startswith("/api/core" + p):
            return True
    return False

# Scan docs
doc_dir = os.path.join(workspace, "docs/manuals")
total = 0
stale = 0

for dirpath, _, filenames in os.walk(doc_dir):
    for fname in filenames:
        if not fname.endswith(".md"):
            continue
        if '_archive' in dirpath:
            continue  # skip archived docs
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
                if not match_route(method, path):
                    stale += 1
                    print(f"⚠️  {rel}:{lineno} → {method} {path}")

            # Pattern 2: bare METHOD /path (no backticks, not inside URLs)
            for m in re.finditer(r'\b(GET|POST|PUT|DELETE|PATCH) (/[a-zA-Z0-9/_{}-]+)(?=[^a-zA-Z0-9/_{}-]|$)', line):
                method = m.group(1)
                path = m.group(2)
                if "http" in line[m.start()-5:m.start()]:  # skip URLs
                    continue
                total += 1
                if not match_route(method, path):
                    stale += 1
                    print(f"⚠️  {rel}:{lineno} → {method} {path}")

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
