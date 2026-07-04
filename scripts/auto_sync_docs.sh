#!/bin/bash
# auto_sync_docs.sh — Auto-generate missing CAPABILITIES.md entries
#
# Closes the gap: verify_doc_sync.sh DETECTS violations,
# auto_sync_docs.sh FIXES them. Together = full auto-sync.
#
# Usage:
#   bash scripts/auto_sync_docs.sh            # detect and auto-fix
#   bash scripts/auto_sync_docs.sh --dry-run  # show what would change
#   bash scripts/auto_sync_docs.sh --force    # overwrite existing stats

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
CAPS="$WORKSPACE/AIPLAT_CAPABILITIES.md"
DRY_RUN=false
FORCE=false
ADDED=0

if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=true; fi
if [ "${1:-}" = "--force" ]; then FORCE=true; fi

# ── Helper: map module name to section heading ──────────────

section_for() {
    local mod="$1"
    local dir="${2:-}"
    case "$dir" in
        *execution*|*loop*|*pipeline*|*langgraph*)    echo "## 一、Harness 执行引擎" ;;
        *memory*|*compression*|*episodic*|*semantic*)  echo "## 二、记忆子系统" ;;
        *ontology_engine*|*class_mapper*|*state_machine*|*graph_index*) echo "## 三、知识引擎（本体）" ;;
        *knowledge*|*retrieval*|*rag*|*hyde*|*rrf*)   echo "## 四、RAG 检索" || echo "## 四附、知识基础设施（Knowledge）" ;;
        *agents*|*agent*)                               echo "## 五、Agent 系统" ;;
        *skills*|*skill*)                               echo "## 六、Skill 系统" ;;
        *engine/skills*)                                echo "## 六、Skill 系统" ;;
        *api/routers*)                                  echo "## 二十一、平台治理" ;;
        *services*)                                     echo "## 一、Harness 执行引擎" ;;
        *management*)                                   echo "## 七、安全与治理" ;;
        *policy*|*gate*|*rbac*|*audit*|*pii*|*secrets*) echo "## 七、安全与治理" ;;
        *observation*|*metrics*|*otel*|*health*)        echo "## 八、可观测性" ;;
        *infrastructure*|*adapter*|*model*)             echo "## 九、模型基础设施" ;;
        *deployment*|*scripts/ops*)                     echo "## 十、部署与运维" ;;
        *infra*)                                        echo "## 二十二、Infra 基础设施" ;;
        *platform*|*tenant*|*billing*|*governance*)     echo "## 二十一、平台治理" ;;
        *approval*)                                     echo "## 三、知识引擎（本体）" ;;
        *)                                              echo "## 十一、扩展与学习" ;;
    esac
}


# ── Step 1: Find new modules not in CAPABILITIES ────────────

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  AUTO SYNC DOCS — Detect + Fix CAPABILITIES.md gaps"
echo "═══════════════════════════════════════════════════════════════"

NEW_MODULES=""
for root in "aiPlat-core/core/harness" "aiPlat-core/core/engine/skills" \
    "aiPlat-core/core/api/routers" "aiPlat-core/core/services" \
    "aiPlat-core/core/management" \
    "aiPlat-platform/auth" "aiPlat-platform/storage" "aiPlat-platform/kb"; do
    if [ ! -d "$WORKSPACE/$root" ]; then continue; fi
    while IFS= read -r f; do
        basename="${f##*/}"
        mod="${basename%.py}"
        # Skip __init__, tests, pycache
        [[ "$basename" == __init__.py ]] && continue
        [[ "$f" == */tests/* ]] && continue
        [[ "$f" == */__pycache__/* ]] && continue
        if ! grep -qi "$mod" "$CAPS" 2>/dev/null; then
            NEW_MODULES="$NEW_MODULES $mod|$f"
        fi
    done < <(find "$WORKSPACE/$root" -name "*.py" -newer "$CAPS" -mtime -7 2>/dev/null)
done

if [ -z "$NEW_MODULES" ]; then
    echo ""
    echo "✅ No new unreferenced modules"
    echo ""
    exit 0
fi

echo ""
echo "Found $(echo "$NEW_MODULES" | wc -w) new modules not in CAPABILITIES.md:"
for entry in $NEW_MODULES; do
    mod="${entry%%|*}"
    path="${entry##*|}"
    dir="$(dirname "$path")"
    echo "  $mod → $(section_for "$mod" "$dir")"
done

# ── Step 2: Auto-generate entries ──────────────────────────

if $DRY_RUN; then
    echo ""
    echo "DRY RUN — would add these entries. Run without --dry-run to apply."
    exit 0
fi

for entry in $NEW_MODULES; do
    mod="${entry%%|*}"
    path="${entry##*|}"
    dir="$(dirname "$path")"
    section="$(section_for "$mod" "$dir")"
    
    # Build short path relative to workspace
    short="${path#$WORKSPACE/}"
    short="${short#aiPlat-core/}"
    short="${short#core/}"
    
    # Generate entry
    entry_line="| $mod | \`$short\` | ✅ | 自动同步 | 已合入 |"
    
    # Insert after the section heading (after the table header + separator line)
    if $FORCE || ! grep -q "$mod" "$CAPS"; then
        # Find the section, insert after the table separator line (second |---| row)
        awk -v section="$section" -v line="$entry_line" '
        BEGIN { inserted=0; in_section=0; past_header=0 }
        {
            if ($0 == section) { in_section=1; past_header=0 }
            if (in_section && past_header == 0 && $0 ~ /^\|------/) { past_header=1 }
            if (in_section && past_header == 1 && $0 ~ /^\|------/ && !inserted) {
                print line
                inserted=1
            }
            print
        }
        ' "$CAPS" > "${CAPS}.tmp" && mv "${CAPS}.tmp" "$CAPS"
        
        if grep -q "$mod" "$CAPS"; then
            echo "  ✅ Added: $mod"
            ADDED=$((ADDED + 1))
        fi
    fi
done

# ── Step 3: Recalculate stats ──────────────────────────────

TOTAL=$(grep -cE '^\|.*\|.*\| ✅' "$CAPS" 2>/dev/null || true)
TOTAL=${TOTAL:-0}
PARTIAL=$(grep -cE '^\|.*\|.*\| ⚠️' "$CAPS" 2>/dev/null || true)
PARTIAL=${PARTIAL:-0}
SUM=$((TOTAL + PARTIAL))

# Update the stats table total row
sed -i '' "s/| \*\*总计\*\* | [0-9]* | [0-9]* | [0-9]* |/| **总计** | **$TOTAL** | **$PARTIAL** | **$SUM** |/" "$CAPS"

# ── Step 4: Sync ROADMAP and CLAUDE counts ─────────────────

ROADMAP="$WORKSPACE/AIPLAT_ROADMAP.md"
CLAUDE="$WORKSPACE/CLAUDE.md"

# Update ROADMAP capability count
if [ -f "$ROADMAP" ]; then
    sed -i '' "s/（[0-9]* 项能力，[0-9]* ✅ + [0-9]* ⚠️）/（${SUM} 项能力，${TOTAL} ✅ + ${PARTIAL} ⚠️）/g" "$ROADMAP"
    sed -i '' "s/代码交叉验证，[0-9]* 项）/代码交叉验证，${SUM} 项）/g" "$ROADMAP"
fi

# Update CLAUDE capability count
if [ -f "$CLAUDE" ]; then
    sed -i '' "s/唯一真相源，[0-9]* 项能力/唯一真相源，${SUM} 项能力/g" "$CLAUDE"
fi

# ══════════════════════════════════════════════════════════════
# Step 4: Auto-recalculate stats table
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 4: Recalculate stats table ━━━"
if python3 "$WORKSPACE/scripts/verify_capability_consistency.py" --fix 2>&1 | head -10; then
    echo "  ✅ Stats table recalculated"
fi

# ══════════════════════════════════════════════════════════════
# Step 5: Deprecated capability detection (Rule 10)
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 5: Detect deprecated capabilities ━━━"
python3 - "$CAPS" "$WORKSPACE" 2>&1 << 'PYEOF_R10'
import sys, re, os, subprocess
caps_file = sys.argv[1]
workspace = sys.argv[2]

with open(caps_file) as f:
    content = f.read()

# Find all code-path references: `path/to/file.py` or `path/to/file.py:123`
refs = re.findall(r'`([a-zA-Z0-9_/.-]+\.py)(?::\d+)?`', content)
changes = 0

for ref in set(refs):
    full_path = os.path.join(workspace, "aiPlat-core/core", ref)
    if os.path.exists(full_path):
        continue

    # Path doesn't exist — check if it was renamed/moved in last 30 days
    dep_path = ref
    moved = False
    try:
        result = subprocess.run(
            ["git", "-C", workspace, "log", "--follow", "--diff-filter=R",
             "--since=30.days.ago", "--oneline", "--", full_path],
            capture_output=True, text=True, timeout=5,
        )
        if result.stdout.strip():
            # File was renamed — extract new name
            new_name = result.stdout.strip().split()[-1] if "=>" not in result.stdout else result.stdout.split("=>")[-1].strip()
            if new_name:
                content = content.replace(ref, new_name)
                changes += 1
                moved = True
                print(f"  🔄 {ref} → {new_name} (renamed)")
    except Exception:
        pass

    if not moved:
        # Grant: 30 days no activity → mark deprecated
        content = content.replace(f"| {ref}", f"| ⚠️ deprecated {ref}")
        changes += 1
        print(f"  ⚠️ {ref} → deprecated (not found, no recent rename)")

if changes > 0:
    with open(caps_file, "w") as f:
        f.write(content)
    print(f"  ✅ {changes} deprecated/renamed entries updated")
else:
    print("  ✅ No deprecated entries found")
PYEOF_R10

# ══════════════════════════════════════════════════════════════
# Step 6: Bare number → reference replacement (Rule 12)
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 6: Replace bare capability counts with references ━━━"
python3 - "$CAPS" "$WORKSPACE" 2>&1 << 'PYEOF_R12'
import sys, re
caps_file = sys.argv[1]
workspace = sys.argv[2]

with open(caps_file) as f:
    caps_content = f.read()

# Get current capability count
current_count = str(caps_content.count("✅"))

# Standard reference format (from DOCUMENT_SYSTEM.md §3.1)
reference = f"（参见 AIPLAT_CAPABILITIES.md 当前计数）"

# Scan all .md files (except CAPABILITIES itself)
import os as _os
ref_count = 0
for root, dirs, files in _os.walk(workspace):
    dirs[:] = [d for d in dirs if d not in (".venv", ".git", "node_modules", "__pycache__", ".pytest_cache", "download", "output", ".aiplat", "archive")]
    for fname in files:
        if not fname.endswith(".md"):
            continue
        fpath = _os.path.join(root, fname)
        if fpath == caps_file:
            continue
        try:
            with open(fpath) as f:
                text = f.read()
        except Exception:
            continue

        # Whole-word match: replace bare current_count with reference (not inside URLs/ports/paths)
        pattern = re.compile(r'(?<!\d)' + current_count + r'(?!\d)')
        if pattern.search(text) and reference not in text:
            new_text = pattern.sub(reference, text, count=1)
            with open(fpath, "w") as f:
                f.write(new_text)
            rel = _os.path.relpath(fpath, workspace)
            print(f"  📝 {rel}: {current_count} → reference")
            ref_count += 1

if ref_count == 0:
    print("  ✅ No bare capability counts found")
else:
    print(f"  ✅ {ref_count} file(s) updated")
PYEOF_R12

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Sync complete: $ADDED new entries, $SUM total (CAPS+ROADMAP+CLAUDE)"
echo "═══════════════════════════════════════════════════════════════"
