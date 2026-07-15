#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  CAPABILITY DISCOVERY — 全系统能力清单发现
#  扫描全仓 Python 代码，聚类发现所有独立的技术能力域
#  对比现有能力合同，报告未覆盖域和并行实现
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
export WORKSPACE

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  CAPABILITY DISCOVERY — 全系统能力清单扫描"
echo "═══════════════════════════════════════════════════════════════"

python3 << 'PYEOF'
import os, re, sys
from pathlib import Path
from collections import defaultdict, Counter

workspace = Path(os.environ["WORKSPACE"])
core_dir = workspace / "aiPlat-core"
platform_dir = workspace / "aiPlat-platform"
infra_dir = workspace / "aiPlat-infra"
contracts_dir = core_dir / "capabilities"

# ── Load existing contracts ──
existing_contracts = set()
if contracts_dir.exists():
    for f in contracts_dir.glob("*.yaml"):
        existing_contracts.add(f.stem)

print(f"\n  Existing contracts: {sorted(existing_contracts)}")

# ── Scan all Python files ──
all_files = []
for base in [core_dir, platform_dir, infra_dir]:
    if not base.exists():
        continue
    for fp in base.rglob("*.py"):
        if "__pycache__" in str(fp) or "node_modules" in str(fp):
            continue
        all_files.append(fp)

print(f"  Scanned: {len(all_files)} Python files across aiPlat-core/platform/infra")

# ── Pattern-based capability discovery ──

# Category 1: Adapter-based (create_adapter / create_infra_*_adapter)
adapter_calls = defaultdict(list)
pattern_adapter = re.compile(
    r'(?:create_adapter|create_infra_(\w+)_adapter)\s*\(\s*["\'](\w+)["\']'
)

for fp in all_files:
    try:
        content = fp.read_text(encoding='utf-8', errors='ignore')
    except:
        continue
    rel = str(fp.relative_to(workspace))
    for m in pattern_adapter.finditer(content):
        cap = m.group(1) or m.group(2)
        if cap:
            adapter_calls[cap].append(rel)

# Category 2: Syscall-based (sys_X functions)
syscall_patterns = defaultdict(list)
pattern_syscall = re.compile(r'\b(sys_\w+)\s*\(')
for fp in all_files:
    try:
        content = fp.read_text(encoding='utf-8', errors='ignore')
    except:
        continue
    rel = str(fp.relative_to(workspace))
    for m in pattern_syscall.finditer(content):
        name = m.group(1)
        syscall_patterns[name].append(rel)

# Category 3: Base class inheritance (class extends BaseTool/BaseSkill/BaseAgent/BaseModelAdapter)
class_patterns = defaultdict(list)
pattern_class = re.compile(
    r'class\s+(\w+)\s*\(\s*(?:BaseTool|BaseSkill|BaseAgent|BaseModelAdapter|BaseLoop|'
    r'DocumentConverter|BaseStore|BaseExecutor)\s*\)'
)
for fp in all_files:
    try:
        content = fp.read_text(encoding='utf-8', errors='ignore')
    except:
        continue
    rel = str(fp.relative_to(workspace))
    for m in pattern_class.finditer(content):
        cls_name = m.group(1)
        class_patterns["tool_cls:" + cls_name].append(rel)

# Category 4: Registry/manager singletons (get_X_registry/get_X_manager)
registry_patterns = defaultdict(list)
pattern_registry = re.compile(r'\b(get_(\w+)_(?:registry|manager|tracker|cache))\s*\(')
for fp in all_files:
    try:
        content = fp.read_text(encoding='utf-8', errors='ignore')
    except:
        continue
    rel = str(fp.relative_to(workspace))
    for m in pattern_registry.finditer(content):
        name = m.group(1)
        registry_patterns[name].append(rel)

# ── Report ──

def _relp(filename):
    """Get relative path from workspace root."""
    return str(filename).replace(str(workspace) + '/', '')

def fmt_count(n):
    return f"{n} callers" if n > 1 else f"{n} caller"

# ── §1: 能力清单 (all discovered domains) ──
print("\n── §1: 全系统能力清单 (by pattern category) ──")

print("\n  [Adapter-based capabilities]")
for cap in sorted(adapter_calls.keys()):
    files = adapter_calls[cap]
    covered = "✓" if cap in existing_contracts else "✗ NEED CONTRACT"
    print(f"    {cap:20s}  {fmt_count(len(files)):15s}  {covered}")

print("\n  [Syscall-based capabilities]")
for name in sorted(syscall_patterns.keys()):
    if name.startswith('sys_') and len(syscall_patterns[name]) >= 2:
        files = syscall_patterns[name]
        covered = "✓" if name.replace('sys_', '') in existing_contracts else "✗ uncovered"
        print(f"    {name:30s}  {fmt_count(len(files)):15s}  {covered}")

print("\n  [Registry/manager singletons]")
for name in sorted(registry_patterns.keys()):
    if len(registry_patterns[name]) >= 3:
        files = registry_patterns[name]
        domain = name.replace('get_', '').replace('_registry', '').replace('_manager', '').replace('_tracker', '').replace('_cache', '')
        covered = "✓" if domain in existing_contracts else "✗ uncovered"
        print(f"    {name:35s}  {fmt_count(len(files)):15s}  {covered}")

# ── §2: 并行实现检测 ──
print("\n── §2: 并行实现检测 (same function name, different files) ──")
sig_patterns = defaultdict(list)
common_funcs = {
    'ocr_frame', 'ocr_image', 'ocr_text', 'ocr_frames', 'ocr_keyframes', 'do_ocr',
    'embed_query', 'encode_text', 'embed', 'get_embedding',
    'retrieve', 'search_pages', 'query_kb', 'fetch_citations',
    'generate_answer', 'summarize', 'classify_text', 'classify',
    'parse_document', 'parse_file', 'parse_image', 'convert',
    'select_model', 'choose_model', 'route_model', 'route',
}
pattern_def = re.compile(r'(?:async\s+)?def\s+(\w+)\s*\(')
for fp in all_files:
    try:
        content = fp.read_text(encoding='utf-8', errors='ignore')
    except:
        continue
    rel = str(fp.relative_to(workspace))
    for m in pattern_def.finditer(content):
        fname = m.group(1)
        if fname in common_funcs:
            sig_patterns[fname].append(rel)

parallel_count = 0
for fname in sorted(sig_patterns.keys()):
    files = sig_patterns[fname]
    if len(files) >= 2:
        unique_matches = set(sig_patterns[fname])
        if len(unique_matches) >= 2:
            parallel_count += 1
            print(f"    def {fname}() — {len(unique_matches)} implementations:")
            for f in sorted(unique_matches):
                print(f"      - {_relp(f)}")

if parallel_count == 0:
    print("    No parallel implementations detected.")

# ── §3: 未覆盖域 ──
print("\n── §3: 未覆盖域 (需要合同但还没有的) ──")
uncovered = []

# Adapter capabilities without contracts
for cap in sorted(adapter_calls.keys()):
    if cap not in existing_contracts and cap not in ('',):
        uncovered.append((cap, 'adapter', adapter_calls[cap]))

# Pick top uncovereds by caller count
uncovered.sort(key=lambda x: -len(x[2]))
if uncovered:
    for cap, cat, files in uncovered[:10]:
        print(f"    {cap:20s}  ({cat}, {len(files)} callers)  → 建议创建 capabilities/{cap}.yaml")
else:
    print("    All adapter-based capabilities covered.")

# ── §4: 自动生成合同草稿 ──
print("\n── §4: 自动生成合同草稿 (_drafts/) ──")
import yaml as _yml

draft_dir = contracts_dir / "_drafts"
draft_dir.mkdir(exist_ok=True)
generated = 0

for cap, cat, files in uncovered:
    if cap in existing_contracts:
        continue
    
    # Find the DEFINITION file (not caller) by searching for def get_*
    auth_file = ""
    factory_name = f"get_{cap}"
    
    # Search for actual function definition
    for base in [core_dir, platform_dir, infra_dir]:
        if not base.exists():
            continue
        for fp in base.rglob("*.py"):
            if "__pycache__" in str(fp):
                continue
            try:
                content = fp.read_text(encoding='utf-8', errors='ignore')
            except:
                continue
            m = re.search(rf'def (get_{cap}_\w+|get_{cap}\b)', content)
            if m:
                fn = m.group(1)
                rel = str(fp.relative_to(workspace))
                if "test" not in rel and "consumer" not in rel:
                    auth_file = rel
                    factory_name = fn
                    break
        if auth_file:
            break
    
    if not auth_file:
        auth_file = files[-1] if files else ""
    
    draft = {
        'capability': cap,
        'description': f"Draft for {cap}",
        'owner': 'core',
        'version': '0.1.0-draft',
        'updated': '2026-07-13',
        'authoritative': {
            'path': auth_file,
            'factory': factory_name,
            'public_symbols': [factory_name],
        },
        'methods': [],
        'consumer_patterns': [str(Path(f).parent).replace(str(workspace)+'/', '') for f in files[:8] if not isinstance(f, Path) or True],
        '_auto_generated': True,
        '_note': 'Review and move to capabilities/ when confirmed',
    }
    
    draft_file = draft_dir / f"{cap}.yaml"
    try:
        with open(draft_file, 'w') as f:
            _yml.dump(draft, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        generated += 1
    except:
        pass

print(f"    Generated {generated} draft contracts in {draft_dir}")

# ── Summary ──
print("\n═══════════════════════════════════════════════════════════════")
print(f"\n  DISCOVERY COMPLETE")
print(f"    Existing contracts:  {len(existing_contracts)}")
print(f"    Adapter capabilities: {len(adapter_calls)}")
print(f"    Syscall capabilities: {len([k for k in syscall_patterns if len(syscall_patterns[k]) >= 2])}")
print(f"    Registry singletons:  {len([k for k in registry_patterns if len(registry_patterns[k]) >= 3])}")
print(f"    Parallel impls:       {parallel_count}")
print(f"    Uncovered domains:    {len(uncovered)}")
print()
PYEOF
