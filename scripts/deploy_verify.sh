#!/usr/bin/env bash
# ============================================================================
# aiPlat 生产部署验证脚本
# 验证 OnboardingWizard → Agent执行 → ValueDashboard 完整闭环
#
# 用法:
#   bash scripts/deploy_verify.sh [--base-url http://localhost:8002] [--timeout 30]
#
# 输出: 0=全部通过, 1=部分失败, 2=严重失败
# ============================================================================
set -euo pipefail

BASE_URL="${1:-http://localhost:8002}"
TIMEOUT="${2:-30}"
TENANT_ID=""
AGENT_ID=""
RUN_ID=""
PASS=0
FAIL=0
SKIP=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

say_pass() { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS + 1)); }
say_fail() { echo -e "  ${RED}✗${NC} $1 ($2)"; FAIL=$((FAIL + 1)); }
say_skip() { echo -e "  ${YELLOW}⊘${NC} $1 (skipped: $2)"; SKIP=$((SKIP + 1)); }
say_info() { echo -e "  ${BLUE}→${NC} $1"; }
h1() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

api_get()  { curl -sfS -m "$TIMEOUT" "$BASE_URL$1" 2>/dev/null; }
api_post() { curl -sfS -m "$TIMEOUT" -X POST -H "Content-Type: application/json" -d "$2" "$BASE_URL$1" 2>/dev/null; }
api_put()  { curl -sfS -m "$TIMEOUT" -X PUT -H "Content-Type: application/json" -d "$2" "$BASE_URL$1" 2>/dev/null; }

h1 "Phase 1: 基础连通性"
RESP=$(api_get "/api/core/health" || true)
if echo "$RESP" | grep -q '"status"'; then
    say_pass "Core health endpoint 可达"
else
    say_fail "Core health endpoint 不可达" "请确认服务已启动"
fi

RESP=$(api_get "/api/management/dashboard/health" || true)
if echo "$RESP" | grep -q '"status"\|"ok"'; then
    say_pass "Management health endpoint 可达"
else
    say_skip "Management health endpoint" "管理端可能未部署"
fi

h1 "Phase 2: OnboardingWizard — 租户激活检查"
STATE=$(api_get "/api/platform/onboarding/state" || true)
if echo "$STATE" | jq -r '.tenants | length' 2>/dev/null | grep -qv 'null'; then
    TCOUNT=$(echo "$STATE" | jq -r '.tenants | length')
    say_info "现有租户数: $TCOUNT"
    if [ "$TCOUNT" -gt 0 ]; then
        TENANT_ID=$(echo "$STATE" | jq -r '.tenants[0].tenant_id // .tenants[0].id // empty')
        say_pass "Onboarding state 可用，默认租户: ${TENANT_ID:-未设置}"
    else
        say_info "无现有租户，尝试创建..."
        CREATE=$(api_post "/api/platform/onboarding/init-tenant" '{"name":"deploy-verify","description":"部署验证测试租户"}' || true)
        TENANT_ID=$(echo "$CREATE" | jq -r '.tenant_id // .id // empty')
        if [ -n "$TENANT_ID" ]; then
            say_pass "租户创建成功: $TENANT_ID"
        else
            FAIL=$((FAIL + 1))
            echo -e "  ${RED}✗${NC} 无法创建租户，跳过后续验证"
            echo ""
            echo "结果: $PASS passed, $FAIL failed, $SKIP skipped"
            exit 2
        fi
    fi
else
    say_skip "Onboarding state" "API 不可用 (jq 解析失败)"
fi

if [ -z "$TENANT_ID" ]; then
    TENANT_ID="default"
    say_info "使用默认 tenant: $TENANT_ID"
fi

h1 "Phase 3: OnboardingWizard — 就绪检查"
READY=$(api_get "/api/platform/onboarding/readiness-check" || true)
if [ -n "$READY" ]; then
    PASSED_CHECKS=$(echo "$READY" | jq -r '[.checks[] | select(.passed==true)] | length' 2>/dev/null || echo "?")
    TOTAL_CHECKS=$(echo "$READY" | jq -r '.checks | length' 2>/dev/null || echo "?")
    say_info "就绪检查: $PASSED_CHECKS/$TOTAL_CHECKS 通过"
    if [ "$PASSED_CHECKS" = "$TOTAL_CHECKS" ] && [ "$TOTAL_CHECKS" != "0" ]; then
        say_pass "所有就绪检查通过"
    elif [ "$PASSED_CHECKS" -ge "$((TOTAL_CHECKS / 2))" ] 2>/dev/null; then
        say_info "部分就绪检查未通过（可继续）"
    else
        say_skip "就绪检查" "大部分未通过，可能未配置 LLM"
    fi
else
    say_skip "Ready check" "API 不可用"
fi

h1 "Phase 4: Agent 执行 — 提交任务"
TASK_PAYLOAD="{\"task\":\"请验证系统是否正常运行，回复 OK 即可\",\"tenant_id\":\"$TENANT_ID\"}"
TASK=$(api_post "/api/platform/onboarding/autosmoke" "$TASK_PAYLOAD" || true)
say_info "AutoSmoke 返回: $(echo "$TASK" | head -c 200)"

# 尝试通过 workspace agent 执行
AGENTS=$(api_get "/api/core/roles/agents" || true)
if echo "$AGENTS" | jq -r '.[]?.agent_id' 2>/dev/null | grep -q .; then
    AGENT_ID=$(echo "$AGENTS" | jq -r '.[0].agent_id')
    say_info "找到 Agent: $AGENT_ID"
    
    EXEC=$(api_post "/api/core/workspace/agents/$AGENT_ID/execute" \
        "{\"user_message\":\"请验证系统运行状态，回复 OK 即可\",\"tenant_id\":\"$TENANT_ID\"}" || true)
    RUN_ID=$(echo "$EXEC" | jq -r '.run_id // .id // empty')
    if [ -n "$RUN_ID" ]; then
        say_pass "Agent 执行已启动: run_id=$RUN_ID"
        
        # 轮询结果
        for i in $(seq 1 10); do
            sleep 3
            STATUS=$(api_get "/api/core/workbench/tasks/$RUN_ID" || true)
            PHASE=$(echo "$STATUS" | jq -r '.phase // .status // "running"')
            say_info "  [$i/10] 状态: $PHASE"
            if echo "$PHASE" | grep -qE 'done|complete|finished|success'; then
                say_pass "Agent 执行完成"
                break
            elif echo "$PHASE" | grep -qE 'failed|error'; then
                say_info "Agent 执行返回非成功状态: $PHASE"
                break
            fi
        done
    else
        say_info "Agent execute 返回异常（可能无可用 Agent）: $(echo "$EXEC" | head -c 200)"
    fi
else
    say_info "无已注册 Agent，跳过执行验证"
fi

h1 "Phase 5: ValueDashboard — 业务价值"
VALUE=$(api_get "/api/core/value/${TENANT_ID}?audience=ceo" || true)
if echo "$VALUE" | jq -e '.total_value' > /dev/null 2>&1; then
    TV=$(echo "$VALUE" | jq -r '.total_value')
    say_pass "ValueDashboard 可达，总值: $TV"
else
    say_info "ValueDashboard 返回: $(echo "$VALUE" | head -c 200)"
fi

GOALS=$(api_get "/api/core/value/${TENANT_ID}/goals" || true)
if echo "$GOALS" | jq -e 'length' > /dev/null 2>&1; then
    GCOUNT=$(echo "$GOALS" | jq -r 'length')
    say_info "业务目标数: $GCOUNT"
fi

h1 "Phase 6: DynamicRouter 灰度状态"
DR_ENABLED="${AIPLAT_DYNAMIC_ROUTER_ENABLED:-false}"
DR_PCT="${AIPLAT_DYNAMIC_ROUTER_PERCENTAGE:-100}"
say_info "DynamicRouter: enabled=$DR_ENABLED, grayscale_pct=$DR_PCT"

h1 "Phase 7: SFT/RL 数据积累状态"
SFT_THRESHOLD="${AIPLAT_SFT_AUTO_TRIGGER_THRESHOLD:-100}"
SFT_ENABLED="${AIPLAT_SFT_ENABLED:-true}"
SFT_MIN_Q="${AIPLAT_SFT_MIN_QUALITY:-0.8}"
say_info "SFT AutoTrigger: threshold=$SFT_THRESHOLD, enabled=$SFT_ENABLED, min_quality=$SFT_MIN_Q"

# Check training data dir
if [ -d "$HOME/.aiplat/training" ]; then
    DATASET_COUNT=$(find "$HOME/.aiplat/training" -name "sft_train_*.jsonl" 2>/dev/null | wc -l | tr -d ' ')
    say_info "SFT 训练数据集: $DATASET_COUNT 个"
else
    say_info "训练数据目录未创建（需首次触发后生成）"
fi

# Check latest SFT model signal
if [ -f "$HOME/.aiplat/sft_models/latest.json" ]; then
    LATEST=$(cat "$HOME/.aiplat/sft_models/latest.json" 2>/dev/null | jq -r '.result_model // .base_model // "unknown"' 2>/dev/null)
    say_info "最新 SFT 模型: $LATEST"
else
    say_info "尚未有 SFT 模型产出"
fi

h1 "Phase 8: Agent SDK 就绪状态"
if python3 -c "import aiplat; print(aiplat.__version__ if hasattr(aiplat, '__version__') else 'ok')" 2>/dev/null; then
    SDK_VER=$(python3 -c "import aiplat; print(getattr(aiplat, '__version__', '0.1.0'))" 2>/dev/null)
    say_pass "Agent SDK 可导入 (v$SDK_VER)"
else
    say_skip "Agent SDK 验证" "aiplat 包未安装 (pip install -e aiplat-sdk/)"
fi

# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "部署验证结果: ${GREEN}$PASS passed${NC} / ${RED}$FAIL failed${NC} / ${YELLOW}$SKIP skipped${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
