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
        *knowledge*|*retrieval*|*rag*|*hyde*|*rrf*|*term_resolver*|*role_view*|*sla_monitor*|*process_orchestrator*|*process_monitor*|*ontology_importer*|*yaml_serializer*|*active_synthesis*|*wiki_quality*) echo "## 三、知识引擎（本体）" ;;
        *learning*)                                      echo "## 十三、演化系统" ;;
        *document*)                                      echo "## 十五、文档智能" ;;
        *agents*|*agent*)                               echo "## 五、Agent 系统" ;;
        *skills*|*skill*)                               echo "## 六、Skill 系统" ;;
        *engine/skills*)                                echo "## 六、Skill 系统" ;;
        *api/routers*)                                  echo "## 二十一、平台治理" ;;
        *services*)                                     echo "## 一、Harness 执行引擎" ;;
        *management*)                                   echo "## 七、安全与治理" ;;
        *policy*|*gate*|*rbac*|*audit*|*pii*|*secrets*|*purpose*) echo "## 七、安全与治理" ;;
        *observation*|*observability*|*metrics*|*otel*|*health*|*usage_tracker*) echo "## 八、可观测性" ;;
        *semantic_gateway*)                             echo "## 二十一、平台治理" ;;
        *infrastructure*|*adapter*|*model*)             echo "## 九、模型基础设施" ;;
        *deployment*|*scripts/ops*)                     echo "## 十、部署与运维" ;;
        *infra*)                                        echo "## 二十二、Infra 基础设施" ;;
        *platform*|*tenant*|*billing*|*governance*)     echo "## 二十一、平台治理" ;;
        *apps/ontology_editor*)                         echo "## 二十一、平台治理" ;;
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
for root in "aiPlat-core/core/harness" "aiPlat-core/core/harness/execution" \
    "aiPlat-core/core/harness/learning" \
    "aiPlat-core/core/harness/document" \
    "aiPlat-core/core/harness/infrastructure" "aiPlat-core/core/harness/infrastructure/gates" \
    "aiPlat-core/core/harness/knowledge" "aiPlat-core/core/harness/observability" \
    "aiPlat-core/core/harness/ontology_engine" "aiPlat-core/core/engine/skills" \
    "aiPlat-core/core/api/routers" "aiPlat-core/core/services" \
    "aiPlat-core/core/management" \
    "aiPlat-platform/apps"; do
    if [ ! -d "$WORKSPACE/$root" ]; then continue; fi
    # Pass 1: committed files (git log)
    while IFS= read -r f; do
        basename="${f##*/}"
        mod="${basename%.py}"
        dirname="$(dirname "$f")"
        # Skip __init__, tests, pycache
        [[ "$basename" == __init__.py ]] && continue
        [[ "$f" == */tests/* ]] && continue
        [[ "$f" == */__pycache__/* ]] && continue
        # Check if module name OR parent directory is already registered
        if ! grep -qi "$mod" "$CAPS" 2>/dev/null && ! grep -qi "$(basename "$dirname")" "$CAPS" 2>/dev/null; then
            NEW_MODULES="$NEW_MODULES $mod|$f"
        fi
    done < <(git -C "$WORKSPACE" log --diff-filter=AM --name-only --since="7 days ago" -- "$root/" 2>/dev/null | grep '\.py$' | sort -u)
    # Pass 2: staged but uncommitted files (git diff --cached)
    while IFS= read -r f; do
        basename="${f##*/}"
        mod="${basename%.py}"
        dirname="$(dirname "$f")"
        [[ "$basename" == __init__.py ]] && continue
        [[ "$f" == */tests/* ]] && continue
        [[ "$f" == */__pycache__/* ]] && continue
        if ! grep -qi "$mod" "$CAPS" 2>/dev/null && ! grep -qi "$(basename "$dirname")" "$CAPS" 2>/dev/null; then
            # Avoid duplicates from pass 1
            if ! echo "$NEW_MODULES" | grep -q "$mod|"; then
                NEW_MODULES="$NEW_MODULES $mod|$f"
            fi
        fi
    done < <(git -C "$WORKSPACE" diff --cached --name-only 2>/dev/null | grep '\.py$' | sort -u)
    # Pass 3: untracked new files that haven't been staged yet (Rule 11-b)
    while IFS= read -r f; do
        basename="${f##*/}"
        mod="${basename%.py}"
        dirname="$(dirname "$f")"
        [[ "$basename" == __init__.py ]] && continue
        [[ "$f" == */tests/* ]] && continue
        [[ "$f" == */__pycache__/* ]] && continue
        if ! grep -qi "$mod" "$CAPS" 2>/dev/null && ! grep -qi "$(basename "$dirname")" "$CAPS" 2>/dev/null; then
            if ! echo "$NEW_MODULES" | grep -q "$mod|"; then
                NEW_MODULES="$NEW_MODULES $mod|$f"
            fi
        fi
    done < <(git -C "$WORKSPACE" ls-files --others --exclude-standard 2>/dev/null | grep '\.py$' | sort -u)
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

# ── Step 4.0: Sync YAML frontmatter total_capabilities ──
echo ""
echo "━━━ Step 4.0: Sync YAML frontmatter ━━━"
python3 - "$CAPS" "$SUM" << 'PYEOF_YAML'
import sys, re
caps_file = sys.argv[1]
count = sys.argv[2]
with open(caps_file) as f:
    content = f.read()
# Update total_capabilities in YAML frontmatter
content = re.sub(r'total_capabilities:\s*\d+', f'total_capabilities: {count}', content)
# Update last_updated date
from datetime import date
today = date.today().strftime('%Y-%m-%d')
content = re.sub(r'last_updated:\s*\d{4}-\d{2}-\d{2}', f'last_updated: {today}', content)
with open(caps_file, 'w') as f:
    f.write(content)
print(f"  ✅ Frontmatter synced: total_capabilities={count}, last_updated={today}")
PYEOF_YAML

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

# ── Step 4.1: Sync all downstream capability count references ─
# Target files + patterns (documented: scripts/doc_sync_targets.yaml)

echo ""
echo "━━━ Step 4.1: Sync downstream capability counts ━━━"

DOWNSTREAM_TARGETS=(
    "docs/README.md|（[0-9]* ✅）|（${SUM} ✅）"
    "docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md|[0-9]* 项能力验证通过|${SUM} 项能力验证通过"
    "docs/whitepaper/verification-protocol.md|changelog.*|[0-9]*|${SUM}"
    "docs/matrix/capability-impact-matrix.md|[0-9]* capabilities|${SUM} capabilities"
    "docs/DOCUMENT_SYSTEM.md|能力数 \`[0-9]*\`|能力数 \`${SUM}\`"
    "AIPLAT_CAPABILITIES.md|（202[0-9]-[0-9][0-9]-[0-9][0-9] — [0-9]*✅）|（2026-07-20 — ${SUM}✅）"
)

for target in "${DOWNSTREAM_TARGETS[@]}"; do
    file="${target%%|*}"
    rest="${target#*|}"
    pattern="${rest%%|*}"
    replacement="${rest#*|}"
    path="$WORKSPACE/$file"
    if [ -f "$path" ]; then
        if sed -i '' "s|${pattern}|${replacement}|g" "$path" 2>/dev/null; then
            echo "  ✓ ${file}"
        fi
    fi
done

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

# ══════════════════════════════════════════════════════════════
# Step 7: Auto-register new public APIs from git diff (Rule 11)
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 7: Auto-register new public APIs from git diff ━━━"
python3 "$WORKSPACE/scripts/verify_docs.py" 2>&1 | grep "新增了.*但未在" | while read -r line; do
  echo "  📝 $line"
done
echo "  ℹ️  Run 'python3 scripts/verify_docs.py' for full report"

# ══════════════════════════════════════════════════════════════
# Step 8: Generate FDE Pipeline Key mapping table from code
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 8: Generate FDE Pipeline Key mapping ━━━"
python3 - "$WORKSPACE" << 'PYEOF_PIPELINE'
import sys, os, re, ast

workspace = sys.argv[1]
target = os.path.join(workspace, "docs/manuals/fde/05-fde-implementation-process.md")

# Parse FDE_PIPELINE_STEPS from fde.py using AST (avoid import side-effects)
fde_src = os.path.join(workspace, "aiPlat-core/core/api/routers/fde.py")
try:
    with open(fde_src) as f:
        tree = ast.parse(f.read())
except Exception as e:
    print(f"  ⚠️  Failed to parse fde.py: {e}")
    sys.exit(0)

pipeline_steps = {}
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if hasattr(target, 'id') and target.id == 'FDE_PIPELINE_STEPS':
                pipeline_steps = ast.literal_eval(node.value)

if not pipeline_steps:
    print("  ⚠️  Could not extract FDE_PIPELINE_STEPS, skipping")
    sys.exit(0)

# Build mapping table rows
logical_map = {"①": "customer", "②": "domain", "③": "diagnosis",
               "④": "pocProfile", "⑤": "deployVersion",
               "⑥": "canaryResult", "⑦": "adopted", "⑧": "monitor"}
rows = []
for s_id, s_def in pipeline_steps.items():
    label = s_def.get("label", s_id)
    keys = sorted(s_def.get("produces", {}).keys())
    key_str = ", ".join(f"`{k}`" for k in keys)
    doc_name = next((v for k, v in logical_map.items() if label.startswith(k)), s_id)
    remarks = "; ".join(
        f"`{k}`={v.get('label','')[:30]}"
        for k, v in s_def.get("produces", {}).items()
    )[:120] or "—"
    rows.append(f"| `{doc_name}` | {key_str} | {len(keys)} 个 | {remarks} |")

new_block = (
    "> 以下由 auto_sync_docs.sh Step 8 自动生成，请勿手动编辑。\n"
    "> 每次运行 auto_sync_docs.sh 时，从 `FDE_PIPELINE_STEPS`（fde.py:673）重新生成。\n\n"
    "| 文档逻辑名 | 代码物理 Key（蛇形） | 粒度 | 备注 |\n"
    "|------|------|:---:|------|\n" + "\n".join(rows)
)

# Replace between sentinel markers (or first-run: wrap existing table)
try:
    with open(target, encoding="utf-8") as f:
        content = f.read()
except FileNotFoundError:
    print("  ⚠️  Target file not found, skipping")
    sys.exit(0)

start_marker = "<!-- AUTO_GEN_PIPELINE_KEY_MAP_START -->"
end_marker = "<!-- AUTO_GEN_PIPELINE_KEY_MAP_END -->"

if start_marker in content:
    content = re.sub(
        re.escape(start_marker) + ".*?" + re.escape(end_marker),
        start_marker + "\n" + new_block + "\n" + end_marker,
        content, flags=re.DOTALL
    )
else:
    # First run: find existing table paragraph and wrap in markers
    pat = r'(> 以上为文档逻辑命名.*?\n\|[^\n]+\n\|[^\n]+\n(?:\|[^\n]*\n)+)'
    m = re.search(pat, content)
    if m:
        content = (content[:m.start()] + start_marker + "\n" + new_block + "\n" + end_marker +
                   content[m.end():])

with open(target, "w", encoding="utf-8") as f:
    f.write(content)
print(f"  ✅ Pipeline Key mapping updated ({len(rows)} steps from FDE_PIPELINE_STEPS)")
PYEOF_PIPELINE

# ══════════════════════════════════════════════════════════════
# Step 6: Content accuracy — detect (规划中) entries with existing code
# ══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Step 6: Content accuracy (planned→implemented drift) ━━━"
python3 << 'PYEOF_ACCURACY'
import os, re
workspace = os.environ.get("WORKSPACE", os.getcwd())
caps = os.path.join(workspace, "AIPLAT_CAPABILITIES.md")
if not os.path.isfile(caps):
    print("  SKIP: CAPABILITIES.md not found")
else:
    with open(caps) as f:
        content = f.read()
    issues = 0
    for line in content.split('\n'):
        if '规划中' not in line or not line.startswith('|'):
            continue
        parts = [c.strip() for c in line.split('|')[1:-1]]
        if len(parts) < 3: continue
        name, filepath = parts[0], parts[1]
        if not ('.py' in filepath or '.yaml' in filepath): continue
        fn = os.path.basename(filepath.split('+')[0].split(':')[0].strip())
        for base in ['aiPlat-core','aiPlat-platform','aiPlat-infra','aiPlat-management']:
            bp = os.path.join(workspace, base)
            if not os.path.isdir(bp): continue
            try:
                result = os.popen(f'find "{bp}" -name "{fn}" -not -path "*/test*" 2>/dev/null').read().strip()
                if result:
                    issues += 1
                    lines = len(open(result.split('\n')[0]).read().split('\n'))
                    print(f"  ⚠️  {name}: file exists ({lines}L) but marked '规划中'")
                    break
            except: pass
    if issues == 0:
        print("  ✅ No content drift detected")
    else:
        print(f"  → {issues} entries need status fix")
PYEOF_ACCURACY

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Sync complete: $ADDED new entries, $SUM total (CAPS+ROADMAP+CLAUDE)"
echo "═══════════════════════════════════════════════════════════════"
