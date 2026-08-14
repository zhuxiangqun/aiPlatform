#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  CAPABILITY GUARD — 能力收敛守护
#  对 capabilities/*.yaml 中的每份合同执行 §A-§E 五项检查
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
CAP_DIR="$WORKSPACE/aiPlat-core/capabilities"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  CAPABILITY CONVERGENCE GUARD — 能力收敛检查"
echo "═══════════════════════════════════════════════════════════════"

if [ ! -d "$CAP_DIR" ]; then
    echo "WARNING: capabilities/ directory not found at $CAP_DIR"
    exit 0
fi

export WORKSPACE CAP_DIR
python3 << 'PYEOF'
import os, sys, re
from pathlib import Path
from datetime import datetime

workspace = Path(os.environ.get("WORKSPACE", os.getcwd()))
cap_dir = Path(os.environ.get("CAP_DIR", workspace / "aiPlat-core" / "capabilities"))

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required — pip install pyyaml")
    sys.exit(1)

contracts = []
for fp in sorted(cap_dir.glob("*.yaml")):
    try:
        with open(fp) as f:
            c = yaml.safe_load(f)
            if c and 'capability' in c and 'authoritative' in c:
                contracts.append(c)
                print(f"  Loaded: {c['capability']} ({fp.name})")
    except Exception as e:
        print(f"  WARNING: failed to parse {fp}: {e}")

if not contracts:
    print("  No capability contracts found. Skipping.")
    sys.exit(0)

print()
errors = 0
warnings = 0

def _grep(pattern, search_dirs):
    """In-memory grep: search pre-built file index instead of spawning subprocess."""
    _ensure_file_index()
    results = []
    for filepath, content in _FILE_INDEX.items():
        if not any(filepath.startswith(d.rstrip('/') + '/') or filepath == d.rstrip('/')
                   for d in search_dirs):
            continue
        for i, line in enumerate(content.split('\n'), 1):
            if re.search(pattern, line):
                results.append(f"{filepath}:{i}:{line.strip()[:120]}")
    return "\n".join(results)


_FILE_INDEX = None

def _ensure_file_index():
    global _FILE_INDEX
    if _FILE_INDEX is not None:
        return
    _FILE_INDEX = {}
    for base in ['aiPlat-core', 'aiPlat-platform', 'aiPlat-infra']:
        base_path = workspace / base
        if not base_path.is_dir():
            continue
        for py_file in base_path.rglob("*.py"):
            if '__pycache__' in str(py_file) or '/tests/' in str(py_file):
                continue
            rel = str(py_file.relative_to(workspace))
            try:
                _FILE_INDEX[rel] = py_file.read_text(encoding='utf-8', errors='replace')
            except Exception:
                pass
    print(f"  File index: {len(_FILE_INDEX)} files loaded")

def _line_to_file(line_str):
    return line_str.split(':', 1)[0] if ':' in line_str else ''

def _is_test(path):
    return '/test' in path or '/tests/' in path or '__pycache__' in path

def _match_path(filepath, allowed_set):
    for a in allowed_set:
        if filepath.startswith(a) or a.endswith(filepath):
            return True
    return False

# ── §A: 重复实现检测 ──
print("── §A: 重复实现检测")
for c in contracts:
    cap = c['capability']
    auth_path = c['authoritative']['path']
    consumers = {con['path'] for con in c.get('consumers', [])}
    legacy = {fix['path'] for fix in c.get('legacy_fixes', [])}
    exceptions = {ex['path'] for ex in c.get('known_exceptions', [])}
    allowed = consumers | legacy | exceptions | {auth_path}
    
    for forbidden in c.get('forbidden_direct_imports', []):
        for base in ['aiPlat-core', 'aiPlat-platform', 'aiPlat-infra']:
            result = _grep(f"import {forbidden}|from {forbidden}", [base + '/'])
            for line in result.split('\n'):
                if not line.strip():
                    continue
                filepath = _line_to_file(line)
                if not filepath or _is_test(filepath):
                    continue
                if 'config_loader' in filepath or 'health_checker' in filepath or 'health_check' in filepath:
                    continue
                if _match_path(filepath, allowed):
                    continue
                cls_name = c['authoritative'].get('class') or c['authoritative'].get('entry_function') or '?'
                print(f"  [ERROR] §A: {filepath} 直接 import '{forbidden}' — {cap} 只能通过 {cls_name}")
                errors += 1

# ── §B: 消费者收敛检测 ──
print("── §B: 消费者收敛检测")
for c in contracts:
    auth_symbols = set(c['authoritative'].get('public_symbols', []))
    factory = c['authoritative'].get('factory', '')
    if factory:
        auth_symbols.add(factory)
    
    for consumer in c.get('consumers', []):
        cpath = consumer['path']
        role = consumer.get('role', '')
        
        if role in ('delegate', 'provider'):
            continue
        
        full_path = workspace / cpath
        if not full_path.exists():
            print(f"  [WARN] §B: {cpath} 文件不存在")
            warnings += 1
            continue
        
        try:
            content = full_path.read_text(encoding='utf-8', errors='ignore')
        except:
            continue
        
        # Check if consumer uses authoritative symbols or via-path
        found = False
        
        # Direct check: authoritative public_symbols
        for s in auth_symbols:
            if s in content and s != 'N/A (function-based)':
                found = True
                break
        
        # Via-path check: last component of via path
        if not found:
            via = consumer.get('via', '')
            if via:
                via_last = via.split('.')[-1]
                found = via_last in content
        
        # Entry function check
        if not found:
            entry = c['authoritative'].get('entry_function', '')
            if entry and entry in content:
                found = True
        
        if not found:
            cls_name = c['authoritative'].get('class') or c['authoritative'].get('entry_function') or '?'
            print(f"  [ERROR] §B: {cpath} 未检测到对 {cls_name} 的导入 — 应使用 {consumer.get('uses', '?')}()")
            errors += 1

# ── §C: 能力缺口检测 ──
print("── §C: 能力缺口")
for c in contracts:
    auth_methods = {m['name'] for m in c.get('methods', [])}
    for consumer in c.get('consumers', []):
        if consumer.get('role') == 'provider':
            continue  # providers don't consume methods
        uses = consumer.get('uses')
        if uses and uses not in auth_methods:
            cls_name = c['authoritative'].get('class') or c['authoritative'].get('entry_function') or '?'
            print(f"  [ERROR] §C: {consumer['path']} 需要 {uses}()，但 {cls_name} 未提供")
            errors += 1

# ── §D: 豁免链追溯 ──
print("── §D: 豁免链追溯")
for base in ['aiPlat-core', 'aiPlat-platform', 'aiPlat-infra']:
    for root, dirs, files in os.walk(str(workspace / base)):
        if 'BOUNDARY.yaml' in files and '__pycache__' not in root:
            bf = os.path.join(root, 'BOUNDARY.yaml')
            try:
                with open(bf) as f:
                    bdata = yaml.safe_load(f) or {}
            except:
                continue
            
            ttl = bdata.get('ttl', '')
            if ttl:
                try:
                    exp = datetime.strptime(ttl, '%Y-%m-%d')
                    if datetime.now() > exp:
                        exempt_dir = os.path.relpath(root, workspace)
                        print(f"  [ERROR] §D: {bf} — TTL {ttl} 已过期，豁免失效")
                        errors += 1
                except ValueError:
                    pass

# ── §E: 签名冲突检测 ──
print("── §E: 签名冲突检测")
for c in contracts:
    auth_path = c['authoritative']['path']
    auth_dir = str(Path(auth_path).parent)
    allowed_files = {auth_path.replace('aiPlat-core/', ''), auth_path}
    for consumer in c.get('consumers', []):
        allowed_files.add(consumer['path'].replace('aiPlat-core/', ''))
        allowed_files.add(consumer['path'])
    
    for method in c.get('methods', []):
        mname = method['name']
        result = _grep(f"def {mname}\\s*\\(", ['aiPlat-core/', 'aiPlat-platform/'])
        for line in result.split('\n'):
            filepath = _line_to_file(line)
            if not filepath or _is_test(filepath):
                continue
            if _match_path(filepath, allowed_files):
                continue
            # Don't flag methods inside the authoritative module itself
            if auth_path in filepath or auth_dir in filepath:
                continue
            cls_name = c['authoritative'].get('class') or c['authoritative'].get('entry_function') or '?'
            print(f"  [WARN] §E: {filepath} 定义了 def {mname}() — 与 {cls_name} 同名，确认非重复实现")
            warnings += 1

# ── §F: 未注册消费者检测 ──
print("── §F: 未注册消费者检测 (reverse §B)")
# Noisy symbols that appear in too many files to be useful for consumer detection
NOISY_SYMBOLS = {
    'create_selected_adapter', 'best_model_for_purpose',
    'create_adapter', 'get_default_model',
}

for c in contracts:
    if c['capability'] in ('llm',):  # sys_llm_generate is ubiquitous, skip
        continue

    cap = c['capability']
    
    # Registered consumers (normalized)
    registered = set()
    for consumer in c.get('consumers', []):
        cp = consumer['path'].replace('aiPlat-core/', '').replace('aiPlat-platform/', '').replace('aiPlat-infra/', '')
        registered.add(cp)
    
    legacy = set()
    for fix in c.get('legacy_fixes', []):
        fp = fix['path'].replace('aiPlat-core/', '').replace('aiPlat-platform/', '').replace('aiPlat-infra/', '')
        legacy.add(fp)
    
    auth_path = c['authoritative']['path'].replace('aiPlat-core/', '').replace('aiPlat-platform/', '').replace('aiPlat-infra/', '')
    auth_dir = str(Path(auth_path).parent) if '/' in auth_path else auth_path
    
    # Build search terms: use capability-specific symbols, skip noisy ones
    search_terms = set()
    cls = c['authoritative'].get('class', '')
    if cls and cls not in ('N/A (function-based)',) and cls not in NOISY_SYMBOLS:
        search_terms.add(cls)
    factory = c['authoritative'].get('factory', '')
    if factory and factory not in NOISY_SYMBOLS:
        search_terms.add(factory)
    entry = c['authoritative'].get('entry_function', '')
    if entry and entry not in NOISY_SYMBOLS:
        search_terms.add(entry)
    
    if not search_terms:
        continue
    
    # Search and deduplicate
    found_files = {}  # filepath → matched symbol
    
    for base in ['aiPlat-core/', 'aiPlat-platform/', 'aiPlat-infra/']:
        for term in search_terms:
            result = _grep(f"\\b{term}\\b", [base])  # word boundary for accuracy
            for line in result.split('\n'):
                filepath = _line_to_file(line)
                if not filepath or _is_test(filepath):
                    continue
                if '__pycache__' in filepath or 'test' in filepath.lower():
                    continue
                # Normalize
                norm = filepath.replace('aiPlat-core/', '').replace('aiPlat-platform/', '').replace('aiPlat-infra/', '')
                if norm in registered or norm in legacy or norm == auth_path:
                    continue
                if filepath.startswith(auth_path) or auth_dir in norm:
                    continue
                # Check consumer_patterns for bulk approval
                patterns = c.get('consumer_patterns', [])
                # Match against both full path and normalized path
                full = filepath  # e.g. aiPlat-core/core/apps/skills/registry.py
                if any(re.search(pat, norm) or re.search(pat, full) for pat in patterns):
                    continue
                if 'config_loader' in filepath or 'health_check' in filepath:
                    continue
                if 'entropy' in filepath or 'BOUNDARY' in filepath:
                    continue
                if norm.endswith('__init__.py') and norm.count('/') <= 2:
                    continue  # top-level __init__ re-exports, not real consumers
                if filepath not in found_files:
                    found_files[filepath] = term
    
    # Report each unique file once per capability
    for filepath, term in sorted(found_files.items()):
        print(f"  [WARN] §F: {filepath} 使用了 {term}（{cap} 能力），但未在 {cap}.yaml 的 consumers 中注册")
        warnings += 1

# ── Summary ──
print()
print("═══════════════════════════════════════════════════════════════")
if errors > 0:
    print(f"  CAPABILITY GUARD FAILED: {errors} error(s), {warnings} warning(s)")
    sys.exit(1)
else:
    print(f"  CAPABILITY GUARD PASSED: 0 errors, {warnings} warning(s)")
    sys.exit(0)
PYEOF

EXIT_CODE=$?
echo ""
if [ $EXIT_CODE -ne 0 ]; then
    echo "  CAPABILITY GUARD: one or more checks FAILED (see above)"
else
    echo "  CAPABILITY GUARD: all checks passed"
fi

# Advisory only for now — uncomment to block CI:
exit $EXIT_CODE
