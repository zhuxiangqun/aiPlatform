#!/bin/bash
# check_doc_sync.sh — pre-commit hook: code → doc dependency checker
# Matches staged files against code_doc_map.yaml, outputs checklist.
# WARNING only, never blocks commit.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
MAP_FILE="$SCRIPT_DIR/code_doc_map.yaml"

if [[ ! -f "$MAP_FILE" ]]; then
  echo "  ⚠️  code_doc_map.yaml not found — skipping doc sync check"
  exit 0
fi

# Get staged + unstaged changes
CHANGED=$(cd "$WORKSPACE" && git diff --name-only HEAD 2>/dev/null || echo "")
STAGED=$(cd "$WORKSPACE" && git diff --cached --name-only 2>/dev/null || echo "")
ALL_CHANGED=$(echo -e "$CHANGED\n$STAGED" | sort -u | grep -v '^$' || echo "")

if [[ -z "$ALL_CHANGED" ]]; then
  exit 0
fi

# Use Python to parse YAML and match
python3 - "$MAP_FILE" "$ALL_CHANGED" "$WORKSPACE" << 'PYEOF'
import sys, os

map_file = sys.argv[1]
changed_raw = sys.argv[2]
workspace = sys.argv[3]

if not changed_raw.strip():
    sys.exit(0)

changed = set(f.strip() for f in changed_raw.split("\n") if f.strip())

# Load YAML
try:
    import yaml
except ImportError:
    # Fallback: try yaml from pip
    import subprocess
    try:
        import yaml
    except ImportError:
        print("  ⚠️  PyYAML not installed — skipping doc sync check")
        print("     Install: pip install pyyaml")
        sys.exit(0)

with open(map_file) as f:
    config = yaml.safe_load(f) or {}

hits = []
seen_docs = set()

# ── Match code_to_docs ──
code_to_docs = config.get("code_to_docs") or {}
for code_path, entry in code_to_docs.items():
    for changed_file in changed:
        # Check if changed file is within the code_path directory
        if changed_file.startswith(code_path) or changed_file == code_path:
            docs = entry.get("docs", [])
            hint = entry.get("hint", "")
            hits.append({
                "code": code_path,
                "file": changed_file,
                "docs": docs,
                "hint": hint,
            })
            for d in docs:
                seen_docs.add(d)
            break  # one hit per code_path

# ── Match routes_to_docs ──
routes_to_docs = config.get("routes_to_docs") or {}
frontend_changed = any("App.tsx" in f or "AppLayout.tsx" in f for f in changed)
for route, entry in routes_to_docs.items():
    if frontend_changed:
        docs = entry.get("docs", [])
        hint = entry.get("hint", "")
        hits.append({
            "code": f"route:{route}",
            "file": "frontend route config",
            "docs": docs,
            "hint": hint,
        })
        for d in docs:
            seen_docs.add(d)
        break  # one hit for all routes

# ── Match source_of_truth ──
sot = config.get("source_of_truth") or {}
for sot_file, sot_entry in sot.items():
    if any(sot_file in f for f in changed):
        downstream = sot_entry.get("downstream", [])
        if downstream:
            hits.append({
                "code": sot_file,
                "file": f"{sot_file} (源文件变更)",
                "docs": downstream,
                "hint": f"单一真相源变更 → 下游 {len(downstream)} 个文件需要同步",
            })

# ── Output ──
if not hits:
    print("✅ 文档同步检查通过 — 当前变更无需更新文档")
    sys.exit(0)

print("")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("📋 文档同步提醒 — 以下文件可能需要更新:")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("")

for i, h in enumerate(hits, 1):
    print(f"  [{i}] {h['code']}")
    print(f"      变更: {h['file']}")
    print(f"      提示: {h['hint']}")
    print(f"      检查: {', '.join(h['docs'][:5])}")
    if len(h['docs']) > 5:
        print(f"            ... 及其他 {len(h['docs']) - 5} 个文件")
    print("")

print(f"  共 {len(hits)} 处需要检查文档同步。")
print(f"  涉及 {len(seen_docs)} 个文档。")
print("")
print("  (此检查为 WARNING 级别，不阻断提交)")
print("  如已更新对应文档，请在 commit message 中标注 doc-sync。")
print("")
PYEOF
