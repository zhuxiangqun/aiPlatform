#!/usr/bin/env bash
# ============================================================================
# Spec 生命周期冒烟测试
# 验证 create → submit → review → trace → dashboard → stable 全链路
#
# 用法:
#   bash scripts/smoke_spec_lifecycle.sh [--base-url http://localhost:8002]
# ============================================================================
set -euo pipefail

BASE_URL="${1:-http://localhost:8002}"
TIMEOUT=30
SPEC_ID="_smoke_test"
PASS=0; FAIL=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; BLUE='\033[0;34m'; NC='\033[0m'
say_pass() { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS+1)); }
say_fail() { echo -e "  ${RED}✗${NC} $1"; FAIL=$((FAIL+1)); }
h1() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

api_get()  { curl -sfS -m "$TIMEOUT" "$BASE_URL$1" 2>/dev/null; }
api_post() { curl -sfS -m "$TIMEOUT" -X POST -H "Content-Type: application/json" -d "$2" "$BASE_URL$1" 2>/dev/null; }

h1 "Phase 1: 清理旧测试数据"
RESP=$(api_post "/api/core/workbench/spec/${SPEC_ID}/mark-stable" '{}' 2>/dev/null || true)
say_pass "旧数据已处理（若存在）"

h1 "Phase 2: 创建 Spec"
RESP=$(api_post "/api/core/workbench/spec/create" \
  "{\"spec_id\":\"${SPEC_ID}\",\"content\":{\"agent_md\":\"冒烟测试 Spec\"},\"created_by\":\"smoke_test\"}" 2>/dev/null)
VERSION=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "?")
STATUS=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "?")
if [ "$STATUS" = "draft" ]; then
    say_pass "Spec 创建: v${VERSION} ${STATUS}"
else
    say_fail "Spec 创建失败: $RESP"
fi

h1 "Phase 3: 提交任务 (关联 Spec)"
RESP=$(api_post "/api/core/workbench/submit" \
  "{\"description\":\"冒烟测试: 请输出 OK\",\"capability\":\"general\",\"spec_id\":\"${SPEC_ID}\"}" 2>/dev/null)
RUN_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null || echo "")
if [ -n "$RUN_ID" ]; then
    say_pass "任务已提交: ${RUN_ID}"
else
    say_fail "任务提交失败: $RESP"
    RUN_ID=""
fi

h1 "Phase 4: 轮询任务状态"
if [ -n "$RUN_ID" ]; then
    for i in $(seq 1 12); do
        sleep 1.5
        RESP=$(api_get "/api/core/workbench/tasks/${RUN_ID}" 2>/dev/null)
        PHASE=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','running'))" 2>/dev/null || echo "running")
        echo -ne "  ${BLUE}→${NC} [${i}/12] ${PHASE}\r"
        if [ "$PHASE" = "completed" ]; then
            echo ""
            say_pass "任务执行完成"
            break
        elif [ "$PHASE" = "failed" ]; then
            echo ""
            say_fail "任务执行失败"
            break
        fi
    done
else
    say_fail "跳过（无 run_id）"
fi

h1 "Phase 5: 验证 Spec 状态 → REVIEW"
RESP=$(api_get "/api/core/workbench/spec/${SPEC_ID}/history" 2>/dev/null)
VER_COUNT=$(echo "$RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('versions',[])))" 2>/dev/null || echo "0")
LATEST_STATUS=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); vs=d.get('versions',[]); print(vs[-1].get('status','?') if vs else '?')" 2>/dev/null || echo "?")
if [ "$LATEST_STATUS" = "review" ]; then
    say_pass "Spec 状态: REVIEW (${VER_COUNT} 个版本)"
else
    say_fail "Spec 状态: ${LATEST_STATUS} (预期 review)"
fi

h1 "Phase 6: 验证 Trace 数据"
RESP=$(api_get "/api/core/workbench/spec/${SPEC_ID}/trace" 2>/dev/null)
STEP_COUNT=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_steps',0))" 2>/dev/null || echo "0")
if [ "$STEP_COUNT" -gt 0 ] 2>/dev/null; then
    say_pass "Trace 数据: ${STEP_COUNT} 步决策链"
else
    say_fail "Trace 数据为空 (可能未关联 Spec)"
fi

h1 "Phase 7: 验证仪表板聚合"
RESP=$(api_get "/api/core/workbench/fde-dashboard" 2>/dev/null)
PENDING=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('pending_decisions',[])))" 2>/dev/null || echo "0")
if [ "$PENDING" -gt 0 ] 2>/dev/null; then
    say_pass "仪表板: ${PENDING} 个待决策"
else
    say_fail "仪表板待决策为空"
fi

h1 "Phase 8: Mark Stable"
RESP=$(api_post "/api/core/workbench/spec/${SPEC_ID}/mark-stable" '{}' 2>/dev/null)
NEW_STATUS=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "?")
if [ "$NEW_STATUS" = "stable" ]; then
    say_pass "状态: → STABLE"
else
    say_fail "Mark stable 失败: $NEW_STATUS"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "冒烟测试结果: ${GREEN}$PASS passed${NC} / ${RED}$FAIL failed${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$FAIL" -gt 0 ]; then exit 1; else exit 0; fi
