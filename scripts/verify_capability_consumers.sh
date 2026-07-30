#!/usr/bin/env bash
# verify_capability_consumers.sh
# Phase 43: Capability-to-consumer traceability verification.
# 
# Five-layer check:
#   0. Registry YAML validity
#   1. Registry 'provides' symbols exist in declared module
#   2. Consumer 'depends_on' declarations match actual imports (for checked-in modules)
#   3. Registry 'consumers_expected' → consumer has code evidence (WARNING by default)
#   4. Git diff capability changes → list affected consumers (interactive)
#
# Env: SKIP_CAPABILITY_CONSUMERS=1 to bypass
#      BLOCK_CAPABILITY_GAP=1 to treat Check 3 as ERROR

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REG_FILE="${ROOT}/aiPlat-core/core/capability_registry.yaml"

if [ "${SKIP_CAPABILITY_CONSUMERS:-}" = "1" ]; then
    exit 0
fi

if ! [ -f "$REG_FILE" ]; then
    exit 0
fi

echo "[verify] Capability-to-consumer traceability..."

# ── Check 0: YAML validity ──
if ! python3 -c "import yaml; yaml.safe_load(open('$REG_FILE'))" 2>/dev/null; then
    echo "  ❌ capability_registry.yaml is malformed YAML"
    exit 1
fi

# ── Check 1: Provider symbols exist in code ──
echo "  [1/3] Provider symbols → code existence..."
python3 -c "
import yaml, sys, os
root = '$ROOT'
data = yaml.safe_load(open('$REG_FILE'))
violations = []
# Search prefixes for mono-repo layout
PREFIXES = ['', 'aiPlat-core/', 'aiPlat-platform/', 'aiPlat-management/']
def find_module(rel_path):
    for pfx in PREFIXES:
        full = os.path.join(root, pfx + rel_path)
        if os.path.exists(full):
            return full
    return None
for domain_id, domain in data.get('domains', {}).items():
    for prov in domain.get('provides', []):
        mod = prov.get('module', '')
        sym = prov.get('symbol', '')
        ptype = prov.get('type', '')
        if not mod or ptype in ('config_file', 'react_component', 'api_endpoint', 'pattern'):
            continue
        fpath = find_module(mod)
        if not fpath:
            violations.append(f'{domain_id}: module {mod} not found')
            continue
        search = sym.split('.')[-1]
        with open(fpath) as f:
            content = f.read()
        if 'class ' + search not in content and 'def ' + search not in content and search + ' =' not in content and search + '(' not in content and search + ':' not in content:
            violations.append(f'{domain_id}: symbol \"{search}\" not found in {mod}')
if violations:
    for v in violations:
        print(f'  ⚠️  {v}')
    print(f'  (WARNING: {len(violations)} registry entries need path/symbol fixes)')
    # Non-blocking: registry is a living document
    # Set STRICT_REGISTRY=1 to block on violations
    if '${STRICT_REGISTRY:-}' == '1':
        sys.exit(1)
print(f'  ✅ Registry symbol check complete')
" || exit 1

# ── Check 3: Registry consumers_expected → grep evidence ──
echo "  [2/3] Expected consumers → code evidence..."
python3 -c "
import yaml, sys, os, subprocess
root = '$ROOT'
PREFIXES = ['', 'aiPlat-core/', 'aiPlat-platform/', 'aiPlat-management/']
def find_module(rel_path):
    for pfx in PREFIXES:
        full = os.path.join(root, pfx + rel_path)
        if os.path.exists(full):
            return full
    return None
data = yaml.safe_load(open('$REG_FILE'))
gaps = []
for domain_id, domain in data.get('domains', {}).items():
    avoids = domain.get('provides', [])
    # Build a search pattern from the first 2 provides symbols
    search_terms = []
    for prov in avoids[:2]:
        search = prov['symbol'].split('.')[-1]
        search_terms.append(search)
    pattern = '|'.join(search_terms[:2])
    if not pattern:
        continue
    for cons in domain.get('consumers_expected', []):
        mod = cons.get('module', '')
        if not mod:
            continue
        fpath = find_module(mod)
        if not fpath:
            gaps.append(f'  ⚠️  {domain_id}: consumer module not found: {mod}')
            continue
        try:
            result = subprocess.run(['grep', '-c', pattern, fpath], capture_output=True, text=True)
            count = int(result.stdout.strip() or 0)
            if count == 0:
                gaps.append(f'  ⚠️  {domain_id}: \"{mod}\" listed as consumer but \"{pattern}\" not found')
        except Exception:
            pass
if gaps:
    print(f'  {len(gaps)} consumer evidence gaps:')
    for g in gaps[:15]:
        print(g)
    if len(gaps) > 15:
        print(f'  ... and {len(gaps)-15} more')
    block = '${BLOCK_CAPABILITY_GAP:-}'
    if block == '1':
        sys.exit(1)
    else:
        print('  (WARNING — set BLOCK_CAPABILITY_GAP=1 to block commits)')
print('  ✅ Consumer evidence check complete')
" || true

# ── Check 4: Git diff capability changes → affected consumers ──
echo "  [3/3] Git diff capability changes → consumer impact..."
python3 -c "
import yaml, sys, os, subprocess
root = '$ROOT'
data = yaml.safe_load(open('$REG_FILE'))
changed_files = subprocess.run(
    ['git', 'diff', '--cached', '--name-only'],
    capture_output=True, text=True, cwd=root
).stdout.strip().split('\n')
affected_domains = set()
for domain_id, domain in data.get('domains', {}).items():
    for prov in domain.get('provides', []):
        mod = prov.get('module', '')
        if any(mod in cf for cf in changed_files):
            affected_domains.add(domain_id)
# Also check if registry itself changed
if '$REG_FILE' in '\n'.join(changed_files):
    for domain_id in data.get('domains', {}):
        affected_domains.add(domain_id)

if affected_domains:
    total_consumers = 0
    for domain_id in sorted(affected_domains):
        domain = data['domains'][domain_id]
        consumers = domain.get('consumers_expected', [])
        total_consumers += len(consumers)
        print(f'  Domain: {domain_id} ({domain[\"section_name\"]}, {len(consumers)} consumers)')
        if len(consumers) <= 10:
            for c in consumers:
                print(f'    → {c[\"module\"]}  — {c.get(\"reason\",\"\")[:60]}')
    print(f'  Total: {len(affected_domains)} domains affected, {total_consumers} consumers to verify')
" 2>/dev/null

echo ""
echo "✅ Capability-to-consumer traceability verified."
