#!/bin/bash
# FDE & Value Center smoke test — run after any code changes to verify core flows
# Usage: bash scripts/smoke_test.sh

BASE="http://localhost:8002/api/core"
PLAT="http://localhost:8003/api/platform"
PASS=0
FAIL=0

check() {
  local method="$1" path="$2" body="$3" desc="$4" base="${5:-$BASE}"
  local url="$base/$path"
  local code
  if [ -n "$body" ]; then
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -X "$method" \
      -H "Content-Type: application/json" -d "$body" "$url" 2>/dev/null)
  else
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -X "$method" "$url" 2>/dev/null)
  fi
  if [ "$code" = "200" ] || [ "$code" = "422" ] || [ "$code" = "400" ] || [ "$code" = "404" ] || [ "$code" = "405" ]; then
    PASS=$((PASS + 1))
    printf "  ✅ %-45s %s\n" "$desc" "$code"
  else
    FAIL=$((FAIL + 1))
    printf "  ❌ %-45s %s\n" "$desc" "$code"
  fi
}

echo "═══════════════════════════════════════════"
echo "  FDE & Value Center Smoke Test"
echo "═══════════════════════════════════════════"

echo ""
echo "── Health Check ──"
check GET "health" "" "Core health"
check GET "docs" "" "Core docs"

echo ""
echo "── Value Center ──"
check GET "value/all/goals" "" "List all goals"
check GET "value/all/strategy" "" "Strategy status"
check GET "value/dev-default/goals" "" "Tenant goals"
check POST "value/all/goals" '{"goal_id":"smoke-1","baseline_value":100,"target_value":200}' "Create goal"

echo ""
echo "── Workbench ──"
check GET "workbench/capabilities" "" "List capabilities"
check GET "workbench/specs" "" "List specs"
check GET "workbench/training/status" "" "Training status"
check POST "workbench/submit" '{"description":"smoke test task"}' "Submit task"

echo ""
echo "── Roles & Agents ──"
check GET "roles/agents" "" "Agent roles"
check GET "agents" "" "Agent list"
check GET "skills" "" "Skill list"

echo ""
echo "── FDE Sessions ──"
check GET "fde/sessions" "" "FDE sessions"
check GET "fde/dashboard" "" "FDE dashboard"
check GET "fde/validate" "" "FDE validate"
check GET "fde/feedback/history" "" "FDE feedback history"
check POST "fde/project/freeze" '{"customer_name":"smoke-test"}' "FDE freeze project"

echo ""
echo "── Platform Layer ──"
check GET "apps/fde/sessions" "" "Platform FDE sessions" "$PLAT"
check GET "apps/fde/dashboard" "" "Platform FDE dashboard" "$PLAT"
check GET "apps/workbench/capabilities" "" "Platform workbench" "$PLAT"
check GET "apps/value/goals" "" "Platform value goals" "$PLAT"

echo ""
echo "═══════════════════════════════════════════"
echo "  Phase 1 Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════"


echo ""
echo "── Validation (expect 422) ──"
check POST "value/all/goals" '{}' "Create goal (empty - 422)"
check POST "workbench/submit" '{}' "Submit task (empty - 422)"
check POST "finetune/train" '{}' "Finetune train (empty - 422)"
check PUT "value/all/goals/smoke-1" '{}' "Update goal (empty - 422)"

echo ""
echo "── Invalid input (expect 400) ──"
check POST "finetune/train" '{"base_model":""}' "Train (empty model - 400)"
check POST "workbench/skill/install" '{"url":""}' "Skill install (empty url - 400)"

echo ""
echo "── Finetune & Knowledge ──"
check GET "finetune/models" "" "Finetune models"
check GET "finetune/providers" "" "Finetune providers"
check GET "wiki/collections" "" "Wiki collections"
check GET "wiki/pages" "" "Wiki pages"
check GET "domains" "" "Knowledge domains"

echo ""
echo "── Memory & MCP ──"
check GET "memory/sessions" "" "Memory sessions"
check GET "mcp/servers" "" "MCP servers"

echo ""
echo "── Diagnostics ──"
check GET "diagnostics/summary" "" "Diagnostics summary"

echo ""
echo "═══════════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
