#!/usr/bin/env python3
"""Check engine state keys against baseline. Flags new business keys not in allowed list."""
import re, os, sys

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baselines", "engine_state_keys.txt")
ENGINE = os.path.join(os.path.dirname(__file__), "..", "aiPlat-core", "core", "harness", "execution", "pipeline_engine.py")

if not os.path.isfile(BASELINE):
    print("⚠️  baseline not found:", BASELINE)
    sys.exit(1)

with open(BASELINE) as f:
    allowed = set()
    debt_keys = set()
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('|')
        key = parts[0]
        status = parts[1] if len(parts) > 1 else "OK"
        allowed.add(key)
        if status == "DEBT":
            debt_keys.add(key)

found = set()
# Scan engine file
if os.path.isfile(ENGINE):
    with open(ENGINE) as f:
        text = f.read()
    for m in re.finditer(r"state\[\'(\w+)\'\]", text):
        found.add(m.group(1))
    for m in re.finditer(r'state\["(\w+)"\]', text):
        found.add(m.group(1))
    for m in re.finditer(r"state\.get\(\'(\w+)\'", text):
        found.add(m.group(1))
    for m in re.finditer(r'state\.get\("(\w+)"', text):
        found.add(m.group(1))

new = found - allowed
if new:
    print(f"❌ {len(new)} new state key(s) not in baseline:")
    for k in sorted(new):
        print(f"   {k}")
    print("\nAction: add to scripts/baselines/engine_state_keys.txt with status=DEBT (if known),")
    print("       or remove hardcoded key from engine, or mark as OK if genuinely generic.")
    sys.exit(1)
else:
    # Report DEBT keys still present
    debt_present = found & debt_keys
    print(f"✅  All {len(found)} state keys in baseline")
    if debt_present:
        print(f"   Known DEBT: {len(debt_present)} key(s) still present (tracked for removal)")
        for k in sorted(debt_present):
            print(f"      DEBT: {k}")
    sys.exit(0)
