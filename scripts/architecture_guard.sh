#!/usr/bin/env bash
# ============================================================================
# architecture_guard.sh — 架构守卫脚本
#
# 零依赖的 grep 级架构违规检查。通过 CI 在每个 PR 上运行。
# 失败 = 架构违规 = 禁止合并。
#
# 检查内容：
#   1. 跨层导入违规（app→core, app→infra, platform→infra, infra→内部）
#   2. 内核硬编码业务知识（角色名、artifact key、评分维度、业务 prompt）
#   3. Infra 硬编码应用名（ai-platform, aiPlat 等）
#   4. Platform 直接实例化 PipelineEngine（应走 CoreFacade）
#   5. App 运行自己的 HTTP 服务器或直接访问数据库
#
# 用法：
#   ./scripts/architecture_guard.sh          # 检查所有层
#   ./scripts/architecture_guard.sh --quick  # 快速模式（仅检查导入方向）
#   ./scripts/architecture_guard.sh --layer core  # 仅检查指定层
# ============================================================================

set -euo

WORKSPACE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

VIOLATIONS=0
MODE="${1:-full}"
LAYER_FILTER="${2:-}"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

check_pass() {
    echo -e "  ${GREEN}PASS${NC}  $1"
}

check_fail() {
    local count=$1
    local desc=$2
    local detail=$3
    echo -e "  ${RED}FAIL${NC}  $desc — ${count} violation(s)"
    if [ -n "$detail" ]; then
        echo "$detail" | while IFS= read -r line; do
            echo -e "        ${RED}→${NC} $line"
        done
    fi
    VIOLATIONS=$((VIOLATIONS + count))
}

grep_py() {
    # Search .py files in a directory, excluding common noise directories
    local dir="$1"
    local pattern="$2"
    if [ ! -d "$dir" ]; then
        return 0
    fi
    find "$dir" -name "*.py" \
        -not -path "*/__pycache__/*" \
        -not -path "*/.pytest_cache/*" \
        -not -path "*/generated/*" \
        -not -path "*/node_modules/*" \
        -not -path "*/.git/*" 2>/dev/null \
        | xargs grep -Hn "$pattern" 2>/dev/null || true
}

grep_py_notest() {
    # Same as grep_py but also excludes test files
    local dir="$1"
    local pattern="$2"
    grep_py "$dir" "$pattern" | grep -v "/tests/" | grep -v "/test_" | grep -v "conftest" || true
}

_count_lines() {
    # Count lines that contain a colon (indicating actual matches), strip whitespace
    local in="$1"
    if [ -z "$in" ]; then
        echo 0
    else
        echo "$in" | grep -c ":" 2>/dev/null || echo 0
    fi
}

# ------------------------------------------------------------------
# Section 1: Cross-Layer Import Violations
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 1: Cross-Layer Import Direction"
echo "═══════════════════════════════════════════════════════════════"

# 1a: app → core (FORBIDDEN)
echo ""
echo "  [1a] aiPlat-app → core ..."
result=$(grep_py_notest "aiPlat-app" 'from core\.\|import core\.')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "app does not import core"
else
    check_fail "$count" "app imports core (must go through platform)" "$result"
fi

# 1b: app → infra (FORBIDDEN)
echo ""
echo "  [1b] aiPlat-app → infra ..."
result=$(grep_py_notest "aiPlat-app" 'from infra\.\|import infra\.')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "app does not import infra"
else
    check_fail "$count" "app imports infra (must go through platform)" "$result"
fi

# 1c: platform → infra (FORBIDDEN)
echo ""
echo "  [1c] aiPlat-platform → infra ..."
result=$(grep_py_notest "aiPlat-platform" 'from infra\.\|import infra\.')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "platform does not import infra"
else
    check_fail "$count" "platform imports infra (must go through core)" "$result"
fi

# 1d: infra → core/platform/app/management (FORBIDDEN)
echo ""
echo "  [1d] aiPlat-infra → internal layers ..."
result=$(grep_py_notest "aiPlat-infra" 'from core\.\|from platform\.\|from app\.\|from management\.')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "infra does not import internal layers"
else
    check_fail "$count" "infra imports internal layers (must be independent)" "$result"
fi

# 1e: core → platform/app (FORBIDDEN)
echo ""
echo "  [1e] aiPlat-core → platform/app ..."
result=$(grep_py_notest "aiPlat-core" 'from platform\.\|from app\.')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "core does not import platform or app"
else
    check_fail "$count" "core imports platform or app (reverse dependency)" "$result"
fi

if [ "$MODE" = "--quick" ]; then
    echo ""
    echo "  Quick mode — skipping deep pattern checks."
    echo ""
    if [ "$VIOLATIONS" -gt 0 ]; then
        echo -e "${RED}═══ ARCHITECTURE GUARD FAILED: $VIOLATIONS violations ═══${NC}"
        exit 1
    else
        echo -e "${GREEN}═══ ARCHITECTURE GUARD PASSED ═══${NC}"
        exit 0
    fi
fi

# ------------------------------------------------------------------
# Section 2: Platform Must Not Directly Instantiate PipelineEngine
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 2: Platform Layer — No Direct Engine Access"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [2a] Platform directly instantiating PipelineEngine ..."
result=$(grep_py_notest "aiPlat-platform" 'PipelineEngine(')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "platform uses CoreFacade (no direct PipelineEngine)"
else
    check_fail "$count" "platform directly instantiates PipelineEngine (use CoreFacade)" "$result"
fi

echo ""
echo "  [2b] Platform importing PipelineEngine from core.harness.execution ..."
result=$(grep_py_notest "aiPlat-platform" 'from core\.harness\.execution\.pipeline_engine')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "platform does not import PipelineEngine directly from harness"
else
    check_fail "$count" "platform bypasses CoreFacade to import PipelineEngine" "$result"
fi

# ------------------------------------------------------------------
# Section 3: Core — Kernel Agnostic (No Business Knowledge)
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 3: Core Harness — Kernel Agnostic"
echo "═══════════════════════════════════════════════════════════════"

HARNESS_DIR="aiPlat-core/core/harness"

echo ""
echo "  [3a] Hardcoded artifact keys in harness..."
result=$(grep_py_notest "$HARNESS_DIR" 'state\["prd"\]\|state\["architecture"\]\|state\["code"\]\|state\["test_report"\]\|state\["test_plan"\]\|state\.get("prd"\|state\.get("architecture"\|state\.get("code"\|state\.get("test_report"')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "no hardcoded artifact keys in harness"
else
    check_fail "$count" "hardcoded artifact keys (use stage.output_artifact)" "$result"
fi

echo ""
echo "  [3b] Hardcoded business role names in harness..."
result=$(grep_py_notest "$HARNESS_DIR" '"pm_agent"\|"architect_agent"\|"programmer_agent"\|"qa_agent"')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "no hardcoded business role names in harness"
else
    check_fail "$count" "hardcoded business role names in harness" "$result"
fi

echo ""
echo "  [3c] Hardcoded scoring dimensions in evaluation..."
result=$(grep_py_notest "aiPlat-core/core/harness/evaluation" '"functionality"\|"product_depth"\|"design_ux"\|"code_architecture"' | grep -v "dimensions\.py" || true)
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "no hardcoded scoring dimensions in evaluation"
else
    check_fail "$count" "hardcoded scoring dimensions (use PipelineStageConfig.scoring_dimensions)" "$result"
fi

echo ""
echo "  [3d] Business SOP prompts in engine..."
result=$(grep_py_notest "aiPlat-core/core/harness/execution" '"You are a strict.*evaluator\|"你是一个严格的')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "no business SOP prompts in engine"
else
    check_fail "$count" "business SOP prompts in engine (move to AGENT.md)" "$result"
fi

echo ""
echo "  [3e] Channel adapter logic in core..."
result=$(grep_py_notest "aiPlat-core/core" 'slack.*signature\|verify_slack\|slack_command\|slack_events\|response_url')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "no channel adapter logic in core"
else
    check_fail "$count" "channel adapter logic in core (move to app)" "$result"
fi

# ------------------------------------------------------------------
# Section 4: Infra — Application Agnostic
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 4: Infra Layer — Application Agnostic"
echo "═══════════════════════════════════════════════════════════════"

INFRA_DIR="aiPlat-infra/infra"

echo ""
echo "  [4a] Application names in infra defaults..."
# Find defaults that are literal strings containing "ai-platform" or "aiPlat"
# but NOT env var names (os.getenv("AIPLAT_*"))
result=$(grep_py_notest "$INFRA_DIR" '=.*"ai.platform\|=.*"aiplat\|=.*"aiPlat\|=.*"ai-platform' | grep -v 'os.getenv\|AIPLAT_' || true)
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "no application-name defaults in infra"
else
    check_fail "$count" "application-name defaults in infra (use env vars with empty fallback)" "$result"
fi

echo ""
echo "  [4b] GPU model name defaults (A100, H100, V100)..."
result=$(grep_py_notest "$INFRA_DIR" '"A100"\|"H100"\|"V100"\|"T4"\|"A10G"')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "no GPU model name defaults in infra"
else
    check_fail "$count" "GPU model name defaults (use empty string)" "$result"
fi

echo ""
echo "  [4c] Developer paths in infra..."
result=$(grep_py_notest "$INFRA_DIR" '/Users/')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "no developer paths in infra"
else
    check_fail "$count" "developer paths in infra" "$result"
fi

echo ""
echo "  [4d] Application-specific cryptographic salts..."
result=$(grep_py_notest "$INFRA_DIR" 'ai.platform.salt\|ai-platform-salt\|aiplat.*salt')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "no application-specific crypto salts in infra"
else
    check_fail "$count" "application-specific crypto salts" "$result"
fi

# ------------------------------------------------------------------
# Section 5: App Layer — No API Server / No Direct DB
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 5: App Layer — No API Server / No Direct DB"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [5a] App running its own HTTP server (FastAPI)..."
result=$(grep_py_notest "aiPlat-app" 'FastAPI(\|uvicorn.run(')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "app does not run its own API server"
else
    check_fail "$count" "app runs its own API server (app is not an API layer)" "$result"
fi

echo ""
echo "  [5b] App accessing database directly (sqlite3, SQLAlchemy)..."
result=$(grep_py_notest "aiPlat-app" 'sqlite3.connect\|create_engine(\|aiosqlite.connect')
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "app does not access database directly"
else
    check_fail "$count" "app accesses database directly (use platform API)" "$result"
fi

# ------------------------------------------------------------------
# Section 6: Core — No Platform-Level Routes
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 6: Core — No Platform-Level HTTP Routes"
echo "═══════════════════════════════════════════════════════════════"

FORBIDDEN_CORE_ROUTES="approvals|tenant_policies|quota|permissions|onboarding|gateway|gate_policies|change_control|chat|channel_adapters|conversations|policy|ops_exports"

echo ""
echo "  [6a] Core has forbidden platform routes..."
existing=$(find "aiPlat-core/core/api/routers" -name "*.py" -not -name "__init__.py" 2>/dev/null \
    | xargs -I{} basename {} .py \
    | grep -wE "$FORBIDDEN_CORE_ROUTES" 2>/dev/null || true)
if [ -z "$existing" ]; then
    check_pass "no platform-level routes in core"
else
    count=$(echo "$existing" | wc -l | tr -d '[:space:]')
    check_fail "$count" "core defines platform-level routes" "$existing"
fi

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"

if [ "$VIOLATIONS" -gt 0 ]; then
    echo -e "${RED}═══ ARCHITECTURE GUARD FAILED: $VIOLATIONS violations ═══${NC}"
    echo ""
    echo "  These violations block merge. Fix options:"
    echo "  1. Move code to the correct layer"
    echo "  2. Use the approved facade/API pattern"
    echo "  3. Replace hardcoded values with configuration fields"
    echo "  4. If this is an approved exception, add an exemption in"
    echo "     scripts/architecture_guard.sh with an architecture review approval"
    echo ""
    exit 1
else
    echo -e "${GREEN}═══ ARCHITECTURE GUARD PASSED — all layers compliant ═══${NC}"
    echo ""
    exit 0
fi
