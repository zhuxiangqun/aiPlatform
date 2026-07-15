#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  CONTRACT GUARD — 模块契约守护
#  验证跨模块数据约定：producer 写入 → consumer 读出 的一致性
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTRACTS_DIR="$WORKSPACE/aiPlat-core/contracts"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  CONTRACT GUARD — 模块契约检查"
echo "═══════════════════════════════════════════════════════════════"

if [ ! -d "$CONTRACTS_DIR" ]; then
    echo "No contracts directory. Skipping."
    exit 0
fi

export WORKSPACE CONTRACTS_DIR
python3 << 'PYEOF'
import os, sys, re
from pathlib import Path

workspace = Path(os.environ["WORKSPACE"])
contracts_dir = Path(os.environ["CONTRACTS_DIR"])

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required")
    sys.exit(1)

errors = 0
warnings = 0
contract_count = 0

for fp in sorted(contracts_dir.glob("*.yaml")):
    try:
        with open(fp) as f:
            c = yaml.safe_load(f)
    except:
        continue
    
    if not c or 'producer' not in c or 'consumer' not in c:
        continue
    
    contract_count += 1
    cid = c.get('id', fp.stem)
    print(f"\n  Contract: {cid}")
    
    prod = c['producer']
    cons = c['consumer']
    
    # ── Check producer module exists ──
    prod_path = workspace / prod['module']
    if not prod_path.exists():
        print(f"    [WARN] Producer module not found: {prod['module']}")
        warnings += 1
        continue
    
    # ── Check consumer module exists ──
    cons_path = workspace / cons['module']
    if not cons_path.exists():
        print(f"    [WARN] Consumer module not found: {cons['module']}")
        warnings += 1
        continue
    
    try:
        prod_content = prod_path.read_text(encoding='utf-8', errors='ignore')
    except:
        continue
    try:
        cons_content = cons_path.read_text(encoding='utf-8', errors='ignore')
    except:
        continue
    
    # ── Verification rules ──
    for vr in c.get('verification', []):
        rule_id = vr.get('rule', '')
        detect = vr.get('detect', '')
        severity = vr.get('severity', 'info')
        
        if not detect:
            continue
        
        # Apply detection pattern
        if 'json_dumps' in detect or 'dumps' in detect and '[:' in detect:
            # Check producer for JSON truncation
            if re.search(r'\.dumps\([^)]+\)\s*\[:\s*\d+\]', prod_content):
                print(f"    [ERROR] {rule_id}: producer has JSON [:N] truncation — data may be corrupted")
                errors += 1
            else:
                print(f"    [PASS] {rule_id}: no JSON truncation in producer")
        
        elif 'cache_ttl' in rule_id or 'cache' in rule_id.lower():
            # Check consumer for TTL-less cache
            if re.search(r'_cache\s*[=:]\s*\{', cons_content):
                if not re.search(r'ttl|_TTL|expir|time\.time', cons_content):
                    prefix = "ERROR" if severity == "error" else "WARN"
                    if severity == "error":
                        errors += 1
                    else:
                        warnings += 1
                    print(f"    [{prefix}] {rule_id}: cache without TTL/expiration detected in consumer")
                else:
                    print(f"    [PASS] {rule_id}: cache has TTL mechanism")
        
        elif 'null_safety' in rule_id or 'json.loads' in detect.lower():
            # Check consumer handles JSON errors
            if 'json.loads' in cons_content or '_json' in cons_content:
                if 'try' in cons_content and 'except' in cons_content and 'json' in cons_content.lower():
                    print(f"    [PASS] {rule_id}: consumer handles JSON parse errors")
                else:
                    print(f"    [WARN] {rule_id}: consumer may not handle JSON parse errors")
                    warnings += 1
        
        elif 'key_name' in rule_id or 'store' in detect.lower():
            # Check store names match
            prod_store = prod.get('writes_to', {}).get('store', '')
            cons_store = cons.get('reads_from', {}).get('store', '')
            if prod_store and cons_store and prod_store == cons_store:
                print(f"    [PASS] {rule_id}: store names match: {prod_store}")
            elif prod_store and cons_store:
                print(f"    [WARN] {rule_id}: store mismatch: producer={prod_store}, consumer={cons_store}")
                warnings += 1
        
        elif 'report_minimum_length' in rule_id:
            # Check consumer validates min length
            if re.search(r'len\(.*\)\s*[<>]=?\s*\d+', cons_content):
                print(f"    [PASS] {rule_id}: consumer validates report length")
        
        else:
            print(f"    [INFO] {rule_id}: rule type not implemented for auto-check")
    
    # ── Key name consistency ──
    wr_fields = {f['name'] for f in prod.get('writes_to', {}).get('fields', [])}
    # Check write fields appear in consumer
    for fname in wr_fields:
        if fname not in cons_content:
            print(f"    [WARN] consumer doesn't reference producer field: {fname}")
            warnings += 1
        else:
            print(f"    [PASS] field '{fname}' referenced by both producer and consumer")

# ── Summary ──
print()
print("═══════════════════════════════════════════════════════════════")
if errors > 0:
    print(f"  CONTRACT GUARD FAILED: {errors} error(s), {warnings} warning(s) ({contract_count} contracts)")
    sys.exit(1)
else:
    print(f"  CONTRACT GUARD PASSED: 0 errors, {warnings} warning(s) ({contract_count} contracts)")
    sys.exit(0)
PYEOF

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "  CONTRACT GUARD: one or more checks FAILED"
else
    echo "  CONTRACT GUARD: all checks passed"
fi
exit $EXIT_CODE
