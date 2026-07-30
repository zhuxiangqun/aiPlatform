#!/usr/bin/env bash
# check_route_menu_sync.sh — Build-time route ↔ sidebar menu consistency check
#
# Extracts route paths from App.tsx and menu keys from AppLayout.tsx,
# then reports orphaned routes and dead menu links.
#
# Usage:
#   bash scripts/check_route_menu_sync.sh          # warning-only, exit 0
#   bash scripts/check_route_menu_sync.sh --strict # block on issues, exit 1

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STRICT=false
[ "${1:-}" = "--strict" ] && STRICT=true

SRC="$ROOT/aiPlat-management/frontend/src"
APP="$SRC/App.tsx"
LAYOUT="$SRC/components/layout/AppLayout.tsx"

if [ ! -f "$APP" ] || [ ! -f "$LAYOUT" ]; then
  echo "⚠️  Route/menu source files not found, skipping check."
  exit 0
fi

TMPDIR="${TMPDIR:-/tmp}"
R="$TMPDIR/aiplat_routes_$$.txt"
M="$TMPDIR/aiplat_menus_$$.txt"
trap 'rm -f "$R" "$M"' EXIT

# ── Extract route paths from App.tsx ─────────────────────────────────
# Format:  path: '/docs'   or   path: "/docs"
# Strip leading /, drop :param segments, sort unique
{
  grep -o "path: *'[^']*'" "$APP" 2>/dev/null || true
  grep -o 'path: *"[^"]*"' "$APP" 2>/dev/null || true
} | sed "s/path: *['\"]//g; s/['\"]//g" | sed 's|^/||; s|/:[^/]*||g' | sort -u > "$R"

# ── Extract menu route keys from AppLayout.tsx ────────────────────────
# Format:  key: '/docs'   or   key: "/docs"
# Only keys starting with / (not _sub_ labels, dividers, user menu)
{
  grep -o "key: *'/[^']*'" "$LAYOUT" 2>/dev/null || true
  grep -o 'key: *"/[^"]*"' "$LAYOUT" 2>/dev/null || true
} | sed "s/key: *['\"]//g; s/['\"]//g" | sed 's|^/||; s|\?.*||' | sort -u > "$M"

# ── Known intentional non-menu routes ─────────────────────────────────
# These routes exist but are deliberately not in the sidebar:
# programmatic, drill-down, utility pages, or accessed through other means.
cat >> "$M" <<'HEREDOC'
alerts
governance
releases
overview
pentest
studio
plugins
workbench
onboarding
onboarding/wizard
app/apps
app/apps/chat
app/builder
app/builder/projects
app/builder/team
app/channels
app/diagrams
app/sessions
approval
approval/history
core/agent-insight
core/approvals
core/jobs
core/learning/artifacts
core/learning/releases
core/learning/rollouts
core/plugins
core/skill-packs
core/skills-rollouts
core/workflows/edit
core/workflows/new
core/workflows/runs
diagnostics/browser-test
diagnostics/capability-boundary
diagnostics/capability-graph
diagnostics/capability-policy
diagnostics/code-intel
diagnostics/context
diagnostics/doctor
diagnostics/exec-backends
diagnostics/graphs
diagnostics/links
diagnostics/model-audit
diagnostics/model-playground
diagnostics/ops
diagnostics/policies
diagnostics/policy-debug
diagnostics/rag-quality
diagnostics/repo
diagnostics/routing-dashboard
diagnostics/routing-replay
diagnostics/run-comparison
diagnostics/runs
diagnostics/smoke
diagnostics/syscalls
diagnostics/traces
diagnostics/workflows
infra/llm-stats
infra/monitoring
infra/network
infra/nodes
infra/services
platform/kb/chat
prompts/app
value-center
value-center/goals
value-center/kpis
value-center/roles
value-center/spec
value-center/strategy
value-center/training
workspace/agents
workspace/mcp
workspace/skills
workspace/skills-lint
workspace/teams
workspace/tools
HEREDOC

# Re-sort after appending exclusions
sort -u -o "$M" "$M"

# ── Compare ──────────────────────────────────────────────────────────
ORPHANS=$(comm -23 "$R" "$M" | grep -v '^$' || true)
DEAD=$(comm -13 "$R" "$M" | grep -v '^$' || true)

HAS=0
if [ -n "$ORPHANS" ]; then
  HAS=1
  echo ""
  echo "⚠️  ORPHANED ROUTES (exist in App.tsx but have no sidebar menu entry):"
  while IFS= read -r r; do echo "   /$r"; done <<< "$ORPHANS"
  echo ""
fi

if [ -n "$DEAD" ]; then
  HAS=1
  echo ""
  echo "⚠️  DEAD MENU LINKS (sidebar key does not match any App.tsx route):"
  while IFS= read -r r; do echo "   /$r"; done <<< "$DEAD"
  echo ""
fi

if [ "$HAS" -eq 0 ]; then
  echo "✅ Route ↔ menu sync: clean (no orphaned routes, no dead links)."
else
  if [ "$STRICT" = true ]; then
    echo "❌ Route ↔ menu sync FAILED. Fix the issues above before committing."
    exit 1
  else
    echo "⚠️  Route ↔ menu sync: issues found (warning-only, build continues)."
    exit 0
  fi
fi
exit 0
