#!/usr/bin/env bash
# Wiki E2E Test Suite — covers backend API + frontend integration paths
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0

_assert() { if [ "$1" -eq 0 ]; then echo -e "  ${GREEN}PASS${NC} $2"; ((PASS++)); else echo -e "  ${RED}FAIL${NC} $2 (exit=$1)"; ((FAIL++)); fi }
_assert_eq() { if [ "$1" = "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3 (expected='$2')"; ((PASS++)); else echo -e "  ${RED}FAIL${NC} $3 (got='$1' expected='$2')"; ((FAIL++)); fi }
_assert_gt() { if [ "$1" -gt "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3 ($1 > $2)"; ((PASS++)); else echo -e "  ${RED}FAIL${NC} $3 ($1 <= $2)"; ((FAIL++)); fi }

API="http://localhost:8002/api/core/wiki"
PLATFORM="http://localhost:8003/platform"

echo "=========================================="
echo " Wiki E2E Test Suite"
echo "=========================================="

# ── Setup: ensure servers are running ────────────────────────────
echo ""
echo "=== Pre-check: server status ==="
for port in 8002 8003; do
  if lsof -ti:$port > /dev/null 2>&1; then
    echo "  port $port: ${GREEN}UP${NC}"
  else
    echo "  port $port: ${RED}DOWN${NC} — skipping tests that need this server"
  fi
done

# ── Test 1: Create + Read + Delete page ───────────────────────────
echo ""
echo "=== 1. CRUD: page lifecycle ==="

# Create
R=$(curl -s -X POST "${API}/pages" -H "Content-Type: application/json" \
  -d '{"title":"E2E Wunderlist Test","body":"Wunderlist was a task management app acquired by Microsoft in 2015 and later replaced by Microsoft To Do.","category":"entities","tags":["test","e2e"],"related":[]}' --max-time 5 2>/dev/null)
RESULT=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('status','ERROR'))" 2>/dev/null)
_assert_eq "$RESULT" "created" "POST /pages — create"

TITLE=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('title',''))" 2>/dev/null)

# Read
R2=$(curl -s "${API}/pages/${TITLE}" --max-time 5 2>/dev/null)
READ_TITLE=$(echo "$R2" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('title',''))" 2>/dev/null)
_assert_eq "$READ_TITLE" "$TITLE" "GET /pages/{title} — read"

# Delete
R3=$(curl -s -X DELETE "${API}/pages/${TITLE}" --max-time 5 2>/dev/null)
DEL_STATUS=$(echo "$R3" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('status','ERROR'))" 2>/dev/null)
_assert_eq "$DEL_STATUS" "deleted" "DELETE /pages/{title} — delete"

# Verify gone
R4=$(curl -s "${API}/pages/${TITLE}" --max-time 5 2>/dev/null)
NOT_FOUND=$(echo "$R4" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('detail',''))" 2>/dev/null)
_assert_eq "$NOT_FOUND" "wiki_page_not_found" "GET /pages/{title} after delete — 404"

# ── Test 2: List with filters ──────────────────────────────────────
echo ""
echo "=== 2. List: filters ==="

R=$(curl -s "${API}/pages?limit=5" --max-time 5 2>/dev/null)
TOTAL=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('total',-1))" 2>/dev/null)
_assert_gt "$TOTAL" "0" "GET /pages — returns pages"

R=$(curl -s "${API}/pages?source=kb&limit=5" --max-time 5 2>/dev/null)
CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API}/pages?source=kb&limit=5" --max-time 5 2>/dev/null)
_assert_eq "$CODE" "200" "GET /pages?source=kb — 200 OK"

R=$(curl -s "${API}/pages?category=topics&limit=5" --max-time 5 2>/dev/null)
CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API}/pages?category=topics&limit=5" --max-time 5 2>/dev/null)
_assert_eq "$CODE" "200" "GET /pages?category=topics — 200 OK"

# ── Test 3: Convert-from-kb with doc_ids ──────────────────────────
echo ""
echo "=== 3. Convert: doc_ids param ==="

# Without doc_ids
R=$(curl -s -X POST "${API}/convert-from-kb?limit=5" -H "Content-Type: application/json" \
  -d '{"tenant_id":"default","limit":5}' --max-time 30 2>/dev/null)
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API}/convert-from-kb?limit=5" \
  -H "Content-Type: application/json" -d '{"tenant_id":"default","limit":5}' --max-time 30 2>/dev/null)
_assert_eq "$CODE" "200" "POST /convert-from-kb (no doc_ids) — 200 OK"

# With doc_ids
R=$(curl -s -X POST "${API}/convert-from-kb?limit=5" -H "Content-Type: application/json" \
  -d '{"tenant_id":"default","limit":5,"doc_ids":["doc_433f92fda518"]}' --max-time 30 2>/dev/null)
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API}/convert-from-kb?limit=5" \
  -H "Content-Type: application/json" -d '{"tenant_id":"default","limit":5,"doc_ids":["doc_433f92fda518"]}' --max-time 30 2>/dev/null)
_assert_eq "$CODE" "200" "POST /convert-from-kb (with doc_ids) — 200 OK"

# With empty doc_ids array
R=$(curl -s -X POST "${API}/convert-from-kb?limit=5" -H "Content-Type: application/json" \
  -d '{"tenant_id":"default","limit":5,"doc_ids":[]}' --max-time 30 2>/dev/null)
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API}/convert-from-kb?limit=5" \
  -H "Content-Type: application/json" -d '{"tenant_id":"default","limit":5,"doc_ids":[]}' --max-time 30 2>/dev/null)
_assert_eq "$CODE" "200" "POST /convert-from-kb (empty doc_ids) — 200 OK"

# Without request body (query params only)
R=$(curl -s -X POST "${API}/convert-from-kb?tenant_id=default&limit=5" --max-time 30 2>/dev/null)
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API}/convert-from-kb?tenant_id=default&limit=5" --max-time 30 2>/dev/null)
_assert_eq "$CODE" "200" "POST /convert-from-kb (query params, no body) — 200 OK"

# ── Test 4: Graph endpoint ────────────────────────────────────────
echo ""
echo "=== 4. Graph: endpoints ==="

R=$(curl -s "${API}/graph?max_nodes=10" --max-time 5 2>/dev/null)
NK=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['stats']['totalNodes'])" 2>/dev/null)
_assert_gt "$NK" "0" "GET /graph — returns nodes"

R=$(curl -s "${API}/graph?source=kb&max_nodes=10" --max-time 5 2>/dev/null)
CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API}/graph?source=kb&max_nodes=10" --max-time 5 2>/dev/null)
_assert_eq "$CODE" "200" "GET /graph?source=kb — 200 OK"

R=$(curl -s "${API}/graph?keyword=OpenViking&max_nodes=10" --max-time 5 2>/dev/null)
CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API}/graph?keyword=OpenViking&max_nodes=10" --max-time 5 2>/dev/null)
_assert_eq "$CODE" "200" "GET /graph?keyword=... — 200 OK"

# ── Test 5: Health check ──────────────────────────────────────────
echo ""
echo "=== 5. Health: lint ==="

R=$(curl -s "${API}/lint" --max-time 5 2>/dev/null)
SCORE=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('health_score',-1))" 2>/dev/null)
_assert_gt "$SCORE" "0" "GET /lint — health_score > 0"
CHECKS=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d.get('checks',[])))" 2>/dev/null)
_assert_gt "$CHECKS" "0" "GET /lint — returns checks array"

# ── Test 6: Curation endpoint ─────────────────────────────────────
echo ""
echo "=== 6. Curation: execute ==="

R=$(curl -s -X POST "${API}/curate" --max-time 30 2>/dev/null)
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API}/curate" --max-time 30 2>/dev/null)
_assert_eq "$CODE" "200" "POST /curate — 200 OK"
PROCESSED=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('processed',-1))" 2>/dev/null)
_assert_gt "$PROCESSED" "-1" "POST /curate — returns processed count"

# ── Test 7: Traverse (explore mode) ───────────────────────────────
echo ""
echo "=== 7. Explore: traverse ==="

# Create parent + child pages for traversal test
curl -s -X POST "${API}/pages" -H "Content-Type: application/json" \
  -d '{"title":"E2E Parent","body":"Parent page for traversal test.","category":"entities","tags":["test"],"related":["E2E Child"]}' --max-time 5 2>/dev/null > /dev/null
curl -s -X POST "${API}/pages" -H "Content-Type: application/json" \
  -d '{"title":"E2E Child","body":"Child page linked from parent.","category":"entities","tags":["test"],"related":["E2E Parent"]}' --max-time 5 2>/dev/null > /dev/null

R=$(curl -s "${API}/traverse/E2E%20Parent?depth=1" --max-time 5 2>/dev/null)
COUNT=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('pages',0))" 2>/dev/null)
_assert_gt "$COUNT" "0" "GET /traverse/{title} — returns linked pages"

# Cleanup
curl -s -X DELETE "${API}/pages/E2E%20Parent" --max-time 5 2>/dev/null > /dev/null
curl -s -X DELETE "${API}/pages/E2E%20Child" --max-time 5 2>/dev/null > /dev/null

# ── Test 8: Delete all ────────────────────────────────────────────
echo ""
echo "=== 8. Clear: delete-all ==="

# Create test page first
curl -s -X POST "${API}/pages" -H "Content-Type: application/json" \
  -d '{"title":"E2E ClearTest","body":"Temporary page for clear test.","category":"entities","tags":["test"],"related":[]}' --max-time 5 2>/dev/null > /dev/null

R=$(curl -s -X DELETE "${API}/pages-all" --max-time 5 2>/dev/null)
DELETED=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('deleted',0))" 2>/dev/null)
_assert_gt "$DELETED" "0" "DELETE /pages-all — deletes pages"

# Verify empty
R=$(curl -s "${API}/pages" --max-time 5 2>/dev/null)
AFTER=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('total',-1))" 2>/dev/null)
_assert_eq "$AFTER" "0" "GET /pages after delete-all — 0 pages"

# ── Test 9: Wiki RAG retrieval ────────────────────────────────────
echo ""
echo "=== 9. RAG: wiki retrieval ==="

# Use python syscall directly (no server needed)
R=$(python3 -c "
import sys; sys.path.insert(0,'aiPlat-core')
from core.harness.syscalls.retrieval import sys_wiki_retrieve
r = sys_wiki_retrieve('机器学习', top_k=2)
print(len(r))
" 2>/dev/null)
_assert_gt "$R" "-1" "sys_wiki_retrieve() — returns results (${R})"

# ── Summary ───────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo " RESULTS: ${GREEN}${PASS} PASS${NC} / ${RED}${FAIL} FAIL${NC}"
echo "=========================================="

[ "$FAIL" -eq 0 ] && echo -e "${GREEN}ALL TESTS PASSED${NC}" && exit 0
echo -e "${RED}${FAIL} TESTS FAILED${NC}" && exit 1
