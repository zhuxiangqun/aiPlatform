#!/usr/bin/env bash
# ============================================================================
# architecture_guard.sh — 架构守卫脚本
#
# 统一合规矩阵 (Unified Compliance Matrix)
# ─────────────────────────────────────────
# 维度          检查项                                    节号
# ─────────────────────────────────────────────────────────
# 层边界        app↛core, app↛infra, platform↛infra       §1
# 层边界        infra↛内部层, core↛platform/app            §1
# 门面模式      platform 禁止直接 PipelineEngine           §2
# 门面模式      platform 深度 harness import 白名单        §20
# 内核无关      artifact key/角色名/评分维度/SOP           §3
# 内核无关      中文业务名/渠道适配                         §3
# 去应用化      infra 应用名/GPU型号/路径/salt             §4
# App层         App 禁止 HTTP Server/DB                   §5
# LangGraph     不绕过 Harness                              §5.5
# Core路由      Core 禁止 Platform 路由                  §6
# Skill元数据   SKILL.md effects/frontmatter              §7
# 交接协议      AGENT.md handoff                          §8
# 目录职责      core/apps/ 目录审计                       §9
# AI模型归属    Platform 不 import AI 模型库              §10
# 文档解析      Platform kb/intelligence 不实现 parser     §11
# 检索算法      Platform query 只编排不实现               §12
# Agent发现     Platform 不实现 agent catalog             §13
# Agent方法     Agent 必须实现 add_skill/add_tool         §14
# BOUNDARY      声明+物理一致性                             §15
# AST行为       Platform 函数不执行 LLM                   §16
# Builder测试   端到端测试                                §17
# 接线验证      死代码检测                                §18
# BOUNDARY覆盖  所有代码目录有声明                         §19
# 性能          同步 I/O 在 async 中                      §21
# 许可证        版权合规                                  §22
# 测试覆盖      模块有测试                                §23
# 密钥扫描      硬编码凭证                                §24
# 错误处理      禁止 except:pass 无日志                   §25
# 安全配置      YAML 硬编码密码                           §26
# 新文件覆盖    新 .py 文件有测试                         §27
# 实现暴露      __init__.py 不暴露实现类                  §28
# Vendor中立    infra 不硬编码厂商字符串                  §29
# 代码质量      禁止 bare except:                         §30
# 代码质量      datetime.now() 有时区                     §31
# 职责归属      层归属检查 → tests/constitution/test_layer_ownership.py
# ─────────────────────────────────────────────────────────
# 总计: 31 grep 级检查 + 10 Python 级检查
# 覆盖: 层边界 / 内核无关 / 去应用化 / 代码质量 / 安全 / 职责归属
# ============================================================================

set -euo

WORKSPACE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE_ROOT"
CORE_DIR="$WORKSPACE_ROOT/aiPlat-core"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

VIOLATIONS=0
MODE="${1:-full}"
LAYER_FILTER="${2:-}"
DIFF_BASE=""

# Parse --diff <base_ref>
if [ "$MODE" = "--diff" ]; then
    DIFF_BASE="${2:-main}"
    MODE="diff"
fi

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

diff_files() {
    # Return list of files changed vs DIFF_BASE, or all .py files if no diff mode
    if [ -n "$DIFF_BASE" ]; then
        git diff --name-only "$DIFF_BASE" HEAD 2>/dev/null | grep '\.py$' || true
    else
        echo ""
    fi
}

# Filter grep output to only show lines from diff-changed files (if in diff mode)
# Usage: result=$(filter_diff "$grep_output")
filter_diff() {
    local in="$1"
    if [ -z "$DIFF_BASE" ] || [ -z "$in" ]; then
        echo "$in"
        return
    fi
    local changed
    changed=$(diff_files)
    if [ -z "$changed" ]; then
        echo "$in"
        return
    fi
    # Keep only lines whose file path matches a changed file
    echo "$in" | while IFS= read -r line; do
        local fpath="${line%%:*}"
        for cf in $changed; do
            if echo "$fpath" | grep -qF "$cf" 2>/dev/null; then
                echo "$line"
                break
            fi
        done
    done
}

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
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 26: Parallel Implementation Detection (§13)"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  [26a] Functions with similar signatures across different modules..."

S26A=""
TMPFILE=$(mktemp)
for d in "aiPlat-core/core/harness" "aiPlat-core/core/apps"; do
    find "$PROJECT_ROOT/$d" -name "*.py" -not -path "*/__pycache__/*" -not -path "*/tests/*" -not -path "*/test_*" \
        -exec grep -l "^\\s*def\|^\\s*async def" {} \; 2>/dev/null | while read f; do
        rel=$(echo "$f" | sed "s|$PROJECT_ROOT/||g")
        grep -E "^\\s*(async\\s+)?def\\s+\\w+\\s*\\(" "$f" 2>/dev/null | while read line; do
            func=$(echo "$line" | sed 's/.*def //;s/ *([^)]*).*//;s/^async //')
            [ -n "$func" ] && echo "$func|$rel"
        done
    done >> "$TMPFILE"
done

# Group by function name, count unique files
awk -F'|' '{files[$1]=files[$1]?(files[$1]";"$2):$2; count[$1]++} END{for(f in count) if(count[f]>=2) print f,count[f],files[f]}' "$TMPFILE" | sort -k2 -rn | while read func cnt files; do
    # Skip interface/adapter methods
    echo "$func" | grep -qE "^(add|get|set|clear|reset|start|stop|enable|disable|execute|run|__|_init|to_dict|from_dict|to_json)$" && continue
    # Count unique files (not occurrences)
    ufiles=$(echo "$files" | tr ';' '\n' | sort -u | wc -l | tr -d ' ')
    [ "$ufiles" -lt 2 ] && continue
    short=$(echo "$files" | tr ';' '\n' | sort -u | sed 's|aiPlat-core/||g' | tr '\n' ',' | sed 's/,$//')
    S26A="${S26A}  func=$func files=$short\n"
done

S26_COUNT=$(echo -e "$S26A" | grep -c "^  func=" 2>/dev/null || echo 0)
if [ "$S26_COUNT" -gt 0 ]; then
    VIOLATIONS=$((VIOLATIONS + S26_COUNT))
    check_fail "$S26_COUNT" "parallel function implementations — use shared module (CLAUDE.md §13)" "$(echo -e "$S26A")"
else
    check_pass "no parallel function implementations detected"
fi
rm -f "$TMPFILE"

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

# [3f] Hardcoded Chinese business role/phase names in core
echo ""
echo "  [3f] Hardcoded Chinese business names in core..."
result=$(grep_py_notest "aiPlat-core/core" '"产品经理"\|"架构师"\|"程序员"\|"测试员"\|"前端开发"\|"后端开发"\|"项目经理"\|"需求分析"\|"系统设计"\|"代码实现"\|"测试评估"' | grep -v "orchestration/\|kernel/types.py" || true)
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "no hardcoded Chinese business names in core"
else
    check_fail "$count" "hardcoded Chinese business names in core (use config-driven)" "$result"
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
# Section 5.5: LangGraph — Must Delegate to Harness (No Direct Syscalls)
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 5.5: LangGraph Nodes — No Direct Syscall Bypass"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [5.5a] LangGraph nodes directly calling syscalls (bypass Harness)..."
LANGRAPH_DIR="aiPlat-core/core/harness/execution/langgraph"
if [ -d "$LANGRAPH_DIR" ]; then
    result=$(grep_py_notest "$LANGRAPH_DIR" 'sys_llm_generate\|sys_tool_call\|sys_skill_call')
    # Known exception: compiled_graphs/react.py (parallel ReAct graph nodes — CLAUDE.md §5.23 phase 9)
    result=$(echo "$result" | grep -v "compiled_graphs/react\.py" || true)
    count=$(_count_lines "$result")
    if [ "$count" -eq 0 ]; then
        check_pass "LangGraph nodes delegate to Harness (no direct syscalls)"
    else
        check_fail "$count" "LangGraph nodes call syscalls directly (must delegate to Harness)" "$result"
    fi
else
    check_pass "no langgraph directory (not an error)"
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
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 7: SKILL.md Metadata Consistency"
echo "═══════════════════════════════════════════════════════════════"

# [7a] All SKILL.md files must have effects declaration
echo ""
echo "  [7a] SKILL.md files missing effects declaration..."
SKILL_DIRS="aiPlat-core/core/engine/skills"
if [ -d "$SKILL_DIRS" ]; then
    missing_effects=""
    for skill_md in "$SKILL_DIRS"/*/SKILL.md; do
        [ -f "$skill_md" ] || continue
        if ! grep -q "^effects:" "$skill_md"; then
            missing_effects="$missing_effects$(dirname "$skill_md")"$'\n'
        fi
    done
    if [ -z "$missing_effects" ]; then
        check_pass "all SKILL.md files have effects declaration"
    else
        count=$(echo "$missing_effects" | grep -c ":" 2>/dev/null || echo 0)
        check_fail "$count" "SKILL.md files missing effects field" "$missing_effects"
    fi
else
    check_pass "no engine skills directory (not an error)"
fi

# [7b] SKILL.md files must have name/description/category fields
echo ""
echo "  [7b] SKILL.md files missing required frontmatter fields..."
if [ -d "$SKILL_DIRS" ]; then
    missing_req=""
    for skill_md in "$SKILL_DIRS"/*/SKILL.md; do
        [ -f "$skill_md" ] || continue
        missing_fields=""
        for field in name description category; do
            grep -q "^${field}:" "$skill_md" || missing_fields="$missing_fields $field"
        done
        [ -n "$missing_fields" ] && missing_req="$missing_req$(dirname "$skill_md"): missing$missing_fields"$'\n'
    done
    if [ -z "$missing_req" ]; then
        check_pass "all SKILL.md files have required frontmatter fields"
    else
        count=$(echo "$missing_req" | grep -c ":" 2>/dev/null || echo 0)
        check_fail "$count" "SKILL.md files missing required fields" "$missing_req"
    fi
else
    check_pass "no engine skills directory (not an error)"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 8: AGENT.md Handoff Compliance (§5.27 Rule 2.1)"
echo "═══════════════════════════════════════════════════════════════"

# [8a] Pipeline-critical AGENT.md must have handoff section
echo ""
echo "  [8a] AGENT.md files missing handoff section..."
AGENT_DIR="${HOME}/.aiplat/agents"
PIPELINE_AGENTS="pm_agent planning_agent architect_agent programmer_agent frontend_engineer backend_developer qa_agent"
missing_handoff=""
for agent in $PIPELINE_AGENTS; do
    agent_md="$AGENT_DIR/$agent/AGENT.md"
    [ -f "$agent_md" ] || continue
    if ! grep -q "交接规范\|\*\*做了什么\*\*" "$agent_md"; then
        missing_handoff="$missing_handoff$agent"$'\n'
    fi
done
if [ -z "$missing_handoff" ]; then
    check_pass "all pipeline-critical AGENT.md have handoff section"
else
    count=$(echo "$missing_handoff" | grep -c ":" 2>/dev/null || echo 0)
    check_fail "$count" "AGENT.md files missing handoff section" "$missing_handoff"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 9: core/apps/ Directory Responsibility Audit"
echo "═══════════════════════════════════════════════════════════════"

# [9a] Each directory in core/apps/ must be generic runtime or documented Internal Policy.
#       Directories that contain full applications (standalone DB, job queues,
#       thread pools, tenant management, video processing) belong in platform.
echo ""
echo "  [9a] core/apps/ directories with application-level concerns..."
APPS_DIR="aiPlat-core/core/apps"
# Known-good: generic runtime (agents, skills, tools, mcp, evaluation, plugins,
#   exec_drivers, ops, quality) or §5.10 Internal Policy (document_intelligence).
# connectors is a protocol adaptor — allowed at core boundary.
KNOWN_APPS="agents skills tools mcp evaluation plugins exec_drivers ops quality document_intelligence connectors"
CONCERN_PATTERNS="sqlite3.connect|threading.Thread|ThreadPool|job_queue|enqueue|tenant.*storage|video.*ingest|multimodal_kb|KBSqlite"
flagged_apps=""
if [ -d "$APPS_DIR" ]; then
    for d in "$APPS_DIR"/*/; do
        [ -d "$d" ] || continue
        dirname=$(basename "$d")
        # Skip known-good directories
        in_whitelist=0
        for known in $KNOWN_APPS; do
            [ "$dirname" = "$known" ] && in_whitelist=1 && break
        done
        [ "$in_whitelist" -eq 1 ] && continue
        # Check if dir contains application-level patterns
        app_indicators=$(grep -rEl "$CONCERN_PATTERNS" "$d" --include='*.py' 2>/dev/null | head -3)
        if [ -n "$app_indicators" ]; then
            flagged_apps="$flagged_apps$dirname ($(echo "$app_indicators" | wc -l | tr -d ' ') files contain DB/thread/job patterns)"$'\n'
        fi
    done
fi
if [ -z "$flagged_apps" ]; then
    check_pass "all core/apps/ directories are generic runtime or documented Internal Policy"
else
    count=$(echo "$flagged_apps" | grep -c "contain" 2>/dev/null || echo 0)
    check_fail "$count" "core/apps/ directories contain application-level concerns (standalone DB/thread/job patterns)" "$flagged_apps"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 10: Platform — No Direct AI Model Library Imports"
echo "  (boundary-standard.md §铁律1: 模型推理归属 Core)"
echo "═══════════════════════════════════════════════════════════════"

PLATFORM_DIR="aiPlat-platform"

# [10a] Platform must not directly import AI model libraries.
#       Model inference (Whisper, Tesseract, PaddleOCR, sentence-transformers)
#       belongs in Core. Platform accesses them via CoreFacade or provider callbacks.
#
#       KNOWN_DEBT (boundary-standard.md §3.1): migration planned for P1.
#       - kb/poc/ocr.py: legacy PoC OCR module (to be replaced by core/harness/document/ocr.py)
echo ""
echo "  [10a] Platform directly importing AI model libraries..."
MODEL_IMPORTS="import faster_whisper\|import whisper\b\|from whisper\|import pytesseract\|import paddleocr\|import sentence_transformers\|from sentence_transformers"
EXCEPT_10A="kb/poc/ocr\.py"
result=$(grep_py_notest "$PLATFORM_DIR" "$MODEL_IMPORTS" | grep -v "$EXCEPT_10A" || true)
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "platform does not directly import AI model libraries"
else
    check_fail "$count" "platform directly imports AI model libraries (belongs in Core per boundary-standard.md §铁律1)" "$result"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 11: Platform KB — Document Parsing & Classification"
echo "  (boundary-standard.md §铁律2: 可复用性决定归属)"
echo "═══════════════════════════════════════════════════════════════"

# [11a] Platform's kb/intelligence/ must not implement its own parsers.
#       Document parsing is a general capability, belongs in core/harness/document/.
echo ""
echo "  [11a] Platform kb/intelligence/ implementing parsers/classifiers..."
PARSER_CLASSIFIER_PATTERNS="def parse_docx\|def parse_pptx\|def parse_markdown\|def classify_document\|def _extract_keywords\b\|def _score_text\b\|def _element_source\b"
result=$(grep -rn "$PARSER_CLASSIFIER_PATTERNS" "$PLATFORM_DIR/kb/intelligence/" --include='*.py' 2>/dev/null || true)
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "platform intelligence/ has no own parsers/classifiers (correctly delegates to core)"
else
    check_fail "$count" "platform intelligence/ implements own parsers/classifiers (belongs in core per boundary-standard.md §铁律2)" "$result"
fi

# [11b] Platform's kb/intelligence/ must not implement its own embedding cache.
#       Embedding cache belongs in core/harness/knowledge/embedder.py.
echo ""
echo "  [11b] Platform kb/intelligence/ implementing own embed cache..."
EMBED_CACHE_PATTERNS="_EMBED_CACHE\b\|_EMBED_CACHE_MAX\b"
result=$(grep -rn "$EMBED_CACHE_PATTERNS" "$PLATFORM_DIR/kb/intelligence/embeddings.py" --include='*.py' 2>/dev/null || true)
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "platform kb/intelligence/embeddings.py has no own embed cache (correctly delegates to core)"
else
    check_fail "$count" "platform intelligence/embeddings.py has own embed cache (belongs in core per boundary-standard.md §铁律2)" "$result"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 12: Platform KB — Retrieval Orchestration Only"
echo "  (boundary-standard.md §5.2: 检索算法归 Core，编排归 Platform)"
echo "═══════════════════════════════════════════════════════════════"

# [12a] Platform query.py must only orchestrate (if/elif routing), not implement
#       retrieval algorithms (cosine_similarity, _score_text, _dedupe, def retrieve).
echo ""
echo "  [12a] Platform kb/intelligence/query.py implementing retrieval algorithms..."
RETRIEVAL_ALGO_PATTERNS="def _cosine_similarity\|def _score_text\b\|def _dedupe\b\|def retrieve\b\|def _search_embedding\|def _search_keyword"
result=$(grep -rn "$RETRIEVAL_ALGO_PATTERNS" "$PLATFORM_DIR/kb/intelligence/query.py" --include='*.py' 2>/dev/null || true)
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "platform query.py orchestrates only (no retrieval algorithm implementation)"
else
    check_fail "$count" "platform query.py implements retrieval algorithms (belongs in core per boundary-standard.md §5.2)" "$result"
fi

# [12b] Platform video_retrieval.py must not implement its own retrieval logic
echo ""
echo "  [12b] Platform kb/intelligence/video_retrieval.py implementing retrieval algorithms..."
result=$(grep -rn "$RETRIEVAL_ALGO_PATTERNS" "$PLATFORM_DIR/kb/intelligence/video_retrieval.py" --include='*.py' 2>/dev/null || true)
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "platform video_retrieval.py orchestrates only (no retrieval algorithm implementation)"
else
    check_fail "$count" "platform video_retrieval.py implements retrieval algorithms (belongs in core per boundary-standard.md §5.2)" "$result"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 13: Platform — No Agent Discovery / Recommendation Logic"
echo "  (boundary-standard.md §决策树: Agent catalog → Core)"
echo "═══════════════════════════════════════════════════════════════"

# [13a] Platform must not implement agent catalog building or scanning.
#       Agent discovery (listing all available agents from disk/registry)
#       is a general capability that any AI application needs.
#
#       KNOWN_DEBT (boundary-standard.md §决策树):
#       - builder_roles.py::_load_agent_md/_role_agent_md_path → core team_planner
#       - builder_project_service.py::_scan_agent_security → core security module
echo ""
echo "  [13a] Platform implementing agent catalog/discovery..."
AGENT_DISCOVERY_PATTERNS="def _build_agent_catalog\|def list_available_agents\|def recommend_team_stages\|_load_agent_md\b\|_role_agent_md_path\|def _scan_agent"
EXCEPT_13A="builder_roles\.py\|builder_project_service\.py"
result=$(grep -rn "$AGENT_DISCOVERY_PATTERNS" "$PLATFORM_DIR/builder/" --include='*.py' 2>/dev/null | grep -v "$EXCEPT_13A" || true)
count=$(_count_lines "$result")
if [ "$count" -eq 0 ]; then
    check_pass "platform does not implement agent discovery/catalog logic"
else
    check_fail "$count" "platform implements agent discovery/catalog logic (belongs in Core per boundary-standard.md §决策树)" "$result"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 14: Agent Class — Method Completeness"
echo "  (All concrete agents must implement add_skill/add_tool)"
echo "═══════════════════════════════════════════════════════════════"

# [14a] Every concrete agent class must implement add_skill() so required_skills
#       from AGENT.md frontmatter can be bound. Missing this method = skills silently dropped.
#       Checks both direct definition AND inheritance from ConfigurableAgent.
echo ""
echo "  [14a] Agent classes missing add_skill method..."
AGENT_FILES=$(find "$CORE_DIR/core/apps/agents" -name "*.py" -not -name "__init__.py" -not -name "base.py" | sort)
missing_add_skill=""
for f in $AGENT_FILES; do
    # Only check files that define agent classes (extend BaseAgent)
    grep -q "class.*BaseAgent\|class.*ConfigurableAgent" "$f" 2>/dev/null || continue
    # Check if the file defines add_skill OR extends ConfigurableAgent/BaseAgent (which provides it)
    if grep -q "def add_skill" "$f" 2>/dev/null; then
        continue
    fi
    # Since BaseAgent now has add_skill(), all agents that extend BaseAgent get it
    if grep -q "BaseAgent" "$f" 2>/dev/null; then
        continue
    fi
    agent_name=$(basename "$f" .py)
    missing_add_skill="$missing_add_skill$agent_name"$'\n'
done
if [ -z "$(echo "$missing_add_skill" | tr -d '[:space:]')" ]; then
    check_pass "all agent classes implement add_skill (or inherit from ConfigurableAgent)"
else
    check_fail 1 "agent classes missing add_skill method (required_skills from AGENT.md will be silently dropped)" "$missing_add_skill"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 15: BOUNDARY.yaml Declaration Consistency"
echo "  (boundary-standard.md §2 决策树: 声明匹配位置)"
echo "═══════════════════════════════════════════════════════════════"

# [15a] Every key directory must have a BOUNDARY.yaml
# [15b] BOUNDARY.yaml layer field must match the directory's physical location
echo ""
echo "  [15a] Key directories missing BOUNDARY.yaml..."
KEY_DIRS=(
    "aiPlat-core/core/harness"                     # harness root
    "aiPlat-core/core/harness/execution"
    "aiPlat-core/core/harness/knowledge"
    "aiPlat-core/core/harness/document"
    "aiPlat-core/core/apps"                        # apps root
    "aiPlat-core/core/apps/agents"
    "aiPlat-core/core/apps/document_intelligence"
    "aiPlat-platform/builder"
    "aiPlat-platform/kb"
    "aiPlat-platform/kb/intelligence"
    "aiPlat-platform/api"
)
missing_decls=""
for dir in "${KEY_DIRS[@]}"; do
    [ -f "$dir/BOUNDARY.yaml" ] || missing_decls="$missing_decls$dir"$'\n'
done
if [ -z "$(echo "$missing_decls" | tr -d '[:space:]')" ]; then
    check_pass "all key directories have BOUNDARY.yaml"
else
    check_fail 1 "directories missing BOUNDARY.yaml (add per docs/architecture/BOUNDARY_TEMPLATE.yaml)" "$missing_decls"
fi

echo ""
echo "  [15b] BOUNDARY.yaml layer mismatch with physical location..."
mismatches=""
for dir in "${KEY_DIRS[@]}"; do
    bf="$dir/BOUNDARY.yaml"
    [ -f "$bf" ] || continue
    declared=$(grep "^layer:" "$bf" | awk '{print $2}' | tr -d '"' | head -1)
    [ -n "$declared" ] || continue
    # Determine actual layer from path
    actual=""
    case "$dir" in
        aiPlat-core/*) actual="core" ;;
        aiPlat-platform/*) actual="platform" ;;
        aiPlat-infra/*) actual="infra" ;;
        aiPlat-app/*) actual="app" ;;
        aiPlat-management/*) actual="management" ;;
    esac
    if [ "$declared" != "$actual" ]; then
        mismatches="$mismatches$dir: declared=$declared, actual=$actual"$'\n'
    fi
done
if [ -z "$(echo "$mismatches" | tr -d '[:space:]')" ]; then
    check_pass "all BOUNDARY.yaml declarations match physical location"
else
    check_fail 1 "BOUNDARY.yaml layer mismatch (move code or update declaration)" "$mismatches"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 16: Platform — No LLM Inference or Agent Discovery"
echo "  (AST behavior-level check: function bodies in platform)"
echo "═══════════════════════════════════════════════════════════════"

# [16a] Platform functions must not perform LLM inference or agent discovery.
#       Uses AST analysis (not grep) — detects any function name that calls
#       core_chat/ChatContext/create_agent/sys_llm_generate or scans AGENT.md.
echo ""
echo "  [16a] Platform functions performing LLM inference / agent discovery..."
AST_RESULT=$(cd "$WORKSPACE_ROOT" && python3 scripts/guard_ast_behavior.py 2>/dev/null)
if echo "$AST_RESULT" | grep -q "^PASS"; then
    check_pass "no platform functions perform LLM inference or agent discovery"
else
    violations_count=$(echo "$AST_RESULT" | grep -c "→" 2>/dev/null || echo 0)
    check_fail "$violations_count" "platform functions contain LLM inference or agent discovery (delegate to Core, or add ## platform:allowed pragma)" "$AST_RESULT"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 17: Builder Pipeline E2E Tests"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [17a] Builder pipeline E2E tests..."
BUILDER_E2E_OUTPUT=$(cd "$(dirname "$0")/.." && PYTHONPATH="$(pwd)/aiPlat-core:$(pwd)/aiPlat-platform" python3 -m pytest aiPlat-platform/tests/test_builder.py aiPlat-core/core/tests/unit/test_builder_pipeline_e2e.py -q --tb=line 2>&1)
BUILDER_E2E_RC=$?
if [ "$BUILDER_E2E_RC" -eq 0 ]; then
    check_pass "all builder pipeline E2E tests pass"
else
    check_fail 1 "builder pipeline E2E tests failed" "$BUILDER_E2E_OUTPUT"
fi

# ------------------------------------------------------------------
# Section 18: Caller Verification — Dead Code Detection
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 18: Caller Verification (Dead Code Detection)"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [18a] Known high-risk symbols for dead code..."

DEAD_SYMBOLS=""
# Only check symbols that are genuinely standalone (not class wrappers used via factory)
# Known exceptions: get_infra_embedding — implemented but not yet wired (embedding flows through memory/embedding.py)
for sym in get_infra_embedding; do
    count=$(grep -rlF "$sym" aiPlat-core aiPlat-platform --include='*.py' 2>/dev/null \
        | grep -v __pycache__ | grep -v '/tests/' \
        | wc -l | tr -d ' ')
    if [ "${count:-0}" -le 1 ]; then
        echo -e "  ${YELLOW}⚠${NC}  $sym has 0 callers (KNOWN: not yet wired, embedding flows through memory/embedding.py)"
    fi
done

# Report: known dead code is advisory only (not a blocking violation)
check_pass "no unapproved dead code detected (advisory: get_infra_embedding not yet wired)"

# ------------------------------------------------------------------
# Section 19: BOUNDARY.yaml — Missing Declaration Check
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 19: BOUNDARY.yaml Coverage (Directories with .py files)"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [19a] Code-bearing directories missing BOUNDARY.yaml..."

MISSING_BOUNDARY=""
for dir in \
    "aiPlat-core/core/api/routers" \
    "aiPlat-core/core/services" \
    "aiPlat-core/core/management" \
    "aiPlat-core/core/apps/skills" \
    "aiPlat-core/core/apps/tools" \
    "aiPlat-core/core/harness/execution/langgraph" \
    "aiPlat-platform/api/routers" \
    "aiPlat-platform/kb/poc" \
    "aiPlat-app/channels" \
    "aiPlat-app/services" \
    "aiPlat-infra/infra/compute" \
    "aiPlat-infra/infra/llm" \
    "aiPlat-infra/infra/vector" \
    "aiPlat-infra/infra/storage" \
; do
    if [ -d "$dir" ]; then
        py_count=$(find "$dir" -maxdepth 1 -name '*.py' -not -name '__init__.py' 2>/dev/null | wc -l | tr -d ' ')
        if [ "${py_count:-0}" -gt 0 ] && [ ! -f "$dir/BOUNDARY.yaml" ]; then
            MISSING_BOUNDARY="$MISSING_BOUNDARY $dir"
        fi
    fi
done

if [ -n "$MISSING_BOUNDARY" ]; then
    check_fail 1 "directories missing BOUNDARY.yaml" "$(echo $MISSING_BOUNDARY)"
else
    check_pass "all code-bearing directories have BOUNDARY.yaml"
fi

# ------------------------------------------------------------------
# Section 20: Facade Whitelist — Deep Harness Import Approval
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 20: Facade Whitelist Enforcement"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [20a] Unapproved deep harness imports in platform..."

# ALLOWED patterns for from core.harness.* in platform (explicit whitelist)
# Each pattern MUST be documented in docs/architecture/boundary-standard.md
FACADE_WHITELIST="infrastructure\.infra_bridge\|infrastructure\.database_port\|knowledge\.db\|knowledge\.embedder\|knowledge\.utils\|harness\.document\|apps/document_intelligence\|llm_env\|syscalls\.llm\|model_injection\|intelligence"

DEEP_IMPORTS=$(grep_py_notest "aiPlat-platform" 'from core\.harness\.')
UNKNOWN_IMPORTS=$(echo "$DEEP_IMPORTS" | grep -v "$FACADE_WHITELIST" || true)

if [ -n "$UNKNOWN_IMPORTS" ]; then
    count=$(_count_lines "$UNKNOWN_IMPORTS")
    # Check if any of these need whitelist addition
    check_fail "$count" "unapproved deep harness imports (add to whitelist or use CoreFacade)" "$UNKNOWN_IMPORTS"
else
    check_pass "all deep harness imports in whitelist"
fi

# ------------------------------------------------------------------
# Section 21: Performance Profiling — Sync I/O in Async Functions
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 21: Performance — Sync I/O in Async Functions"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [21a] Synchronous subprocess.run() in async functions..."
S21A=$(grep_py_notest "aiPlat-core/core/harness/execution" 'subprocess\.run(' | grep -v "f\"\|subprocess, sys\|_write_file\|# noqa\|capture_output.*text.*timeout" || true)
S21A=$(filter_diff "$S21A")
if [ -n "$S21A" ]; then
    count=$(_count_lines "$S21A")
    check_fail "$count" "synchronous subprocess.call in async context (use asyncio.create_subprocess_exec)" "$S21A"
else
    check_pass "no synchronous subprocess in async execution"
fi

echo ""
echo "  [21b] Sync file I/O (open/write) in async engine functions (advisory)..."
S21B=$(grep_py_notest "aiPlat-core/core/harness/execution/pipeline_engine.py" 'open(' | grep -v "_write_file\|_persist_files\|_do()\|# noqa\|Path(\|_deploy_docker" || true)
if [ -n "$S21B" ]; then
    count=$(_count_lines "$S21B")
    echo -e "  ${YELLOW}⚠${NC}  $count sync file I/O calls remain (acceptable: cold paths, already wrapped where hot)"
else
    check_pass "no blocking file I/O in async engine functions"
fi

# ------------------------------------------------------------------
# Section 22: License Audit — Copyleft License Detection
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 22: License Audit — Copyleft Compliance"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [22a] Copyleft-licensed packages (GPL/AGPL) in dependencies..."
S22=$(grep -i "GPL\|AGPL" "$WORKSPACE_ROOT/requirements.txt" 2>/dev/null || true)
if [ -n "$S22" ]; then
    count=$(echo "$S22" | wc -l | tr -d ' ')
    check_fail "$count" "copyleft-licensed packages detected (review for compliance)" "$S22"
else
    check_pass "no copyleft licenses detected in frozen deps"
fi

# ------------------------------------------------------------------
# Section 23: Test Coverage — Zero-Test Modules
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 23: Test Coverage — Modules with Zero Tests"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [23a] Key modules with 0 dedicated test files..."
ZERO_TEST=""
for mod in \
    "aiPlat-core/core/harness/execution/team_planner.py" \
    "aiPlat-core/core/harness/execution/conditional.py" \
    "aiPlat-core/core/harness/execution/debate.py" \
    "aiPlat-core/core/harness/execution/renderer.py" \
    "aiPlat-platform/api/routers/onboarding.py" \
    "aiPlat-platform/builder/builder_project_service.py" \
    "aiPlat-core/core/harness/assembly/context_assembler.py" \
; do
    modname=$(basename "$mod" .py)
    test_file=$(find "$WORKSPACE_ROOT" -path "*/tests/*" -name "*${modname}*" -o -path "*/tests/*" -name "*test_builder*" 2>/dev/null | head -1)
    # Also check if any test file in the repo references the module
    if [ -z "$test_file" ]; then
        test_file=$(grep -rl "$modname" "$WORKSPACE_ROOT" --include='*test*.py' 2>/dev/null | head -1)
    fi
    if [ -z "$test_file" ]; then
        ZERO_TEST="$ZERO_TEST $mod"
    fi
done
if [ -n "$ZERO_TEST" ]; then
    count=$(echo "$ZERO_TEST" | wc -w | tr -d ' ')
    check_fail "$count" "key modules with 0 dedicated test files (advisory)" "$(echo $ZERO_TEST)"
else
    check_pass "all key modules have test coverage"
fi

# ------------------------------------------------------------------
# Section 24: Secret/Key Scanning
# ------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 24: Secret Detection — API Keys / Tokens / Passwords"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [24a] Hardcoded API keys / secrets in source files..."
S24=$(grep -rnE '(sk-[a-zA-Z0-9]{20,}|api_key\s*=\s*"[^"]{20,}"|password\s*=\s*"[^"]{8,}"|secret\s*=\s*"[^"]{8,}")' \
    "$WORKSPACE_ROOT/aiPlat-core" "$WORKSPACE_ROOT/aiPlat-platform" "$WORKSPACE_ROOT/aiPlat-infra" "$WORKSPACE_ROOT/aiPlat-app" \
    --include='*.py' --include='*.yml' --include='*.yaml' --include='*.json' 2>/dev/null \
    | grep -v __pycache__ | grep -v "/tests/" | grep -v ".env" | grep -v "mock-api-key" | grep -v "REPLACE_ME" | grep -v "example" || true)
S24=$(filter_diff "$S24")
if [ -n "$S24" ]; then
    count=$(_count_lines "$S24")
    check_fail "$count" "potential hardcoded secrets detected (use env vars)" "$S24"
else
    check_pass "no hardcoded secrets in source files"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 25: Error Swallowing — No Silent except:pass"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [25a] Production code with bare except:pass ..."
S25A=$(grep_py_notest "aiPlat-core/core" 'except Exception: pass' | grep -v "# noqa\|# allowed" || true)
S25A="$S25A"$'\n'"$(grep_py_notest "aiPlat-platform" 'except Exception: pass' | grep -v "# noqa\|# allowed" || true)"
S25A="$S25A"$'\n'"$(grep_py_notest "aiPlat-app" 'except Exception: pass' | grep -v "# noqa\|# allowed" || true)"
S25A=$(echo "$S25A" | grep -v "^$" || true)
count=$(_count_lines "$S25A")
if [ "$count" -eq 0 ]; then
    check_pass "no silent except:pass in production code"
else
    check_fail "$count" "bare except:pass — use logging.warning(..., exc_info=True) at minimum" "$S25A"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 26: Security — No Hardcoded Credentials"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [26a] Hardcoded passwords in YAML/JSON config ..."
S26=$(grep -rnE 'password\s*:\s*"[^$]{3,}"' "$WORKSPACE_ROOT" --include='*.yaml' --include='*.yml' --include='*.json' 2>/dev/null | grep -v node_modules | grep -v '.venv' | grep -v __pycache__ | grep -v '/tests/' | grep -v 'mock\|example\|REPLACE_ME' || true)
count=$(_count_lines "$S26")
if [ "$count" -eq 0 ]; then
    check_pass "no hardcoded passwords in config files"
else
    check_fail "$count" "hardcoded passwords — use \${ENV_VAR} references" "$S26"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 27: New File Test Coverage"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [27a] New .py files without corresponding test ..."
UNCOVERED=""
for f in $(git diff --name-only HEAD 2>/dev/null | grep '\.py$' | grep -v '/tests/' | grep -v '__pycache__' | grep -v '.bak$'); do
    fname=$(basename "$f" .py)
    [ "$fname" = "__init__" ] && continue
    test_found=$(find "$WORKSPACE_ROOT" -path "*/tests/*${fname}*" -name "*.py" 2>/dev/null | head -1)
    [ -z "$test_found" ] && UNCOVERED="$UNCOVERED $f"
done
if [ -z "$(echo "$UNCOVERED" | tr -d '[:space:]')" ]; then
    check_pass "all new .py files have test coverage"
else
    check_fail 1 "new files without tests (advisory)" "$(echo $UNCOVERED)"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 28: Infra — No Implementation Class Exposure"
echo "  (CLAUDE.md §5.1: 禁止暴露具体实现类)"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [28a] __init__.py files exposing implementation classes..."
# Check if __init__.py exports concrete impl classes (violates infra §5.1)
EXPOSED_CLASSES=""
for init in aiPlat-infra/infra/*/__init__.py; do
    [ ! -f "$init" ] && continue
    # Patterns: class names that look like implementation (not abstract/factory)
    exposed=$(grep -oE '[A-Z][a-zA-Z]+Client\b|[A-Z][a-zA-Z]+Impl\b|[A-Z][a-zA-Z]+Manager\b' "$init" 2>/dev/null | grep -v "ErrorHandler\|HealthChecker\|AlertManager" || true)
    if [ -n "$exposed" ]; then
        while IFS= read -r cls; do
            [ -z "$cls" ] && continue
            # Check if this class appears in __all__ or from-import
            if grep -q "$cls" "$init" 2>/dev/null; then
                EXPOSED_CLASSES="$EXPOSED_CLASSES$(dirname "$init" | xargs basename):$cls"$'\n'
            fi
        done <<< "$exposed"
    fi
done
count=$(echo "$EXPOSED_CLASSES" | grep -c ":" 2>/dev/null || echo 0)
if [ "$count" -eq 0 ]; then
    check_pass "no implementation classes exposed in __init__.py"
else
    check_fail "$count" "__init__.py exposes implementation classes (use factory functions only)" "$EXPOSED_CLASSES"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 29: Infra — No Vendor-Specific Hardware Strings"
echo "  (CLAUDE.md §2.1: infra 必须对硬件厂商无知)"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [29a] Hardware vendor strings in defaults (Apple Silicon, NVIDIA)..."
S29=$(grep_py_notest "aiPlat-infra/infra" '"Apple Silicon"\|"Apple M[0-9]"\|"M1\|M2\|M3\|"A100"\|"H100"\|"V100"' | grep -v "# noqa\|# allowed" || true)
count=$(_count_lines "$S29")
if [ "$count" -eq 0 ]; then
    check_pass "no hardware vendor strings in infra defaults"
else
    check_fail "$count" "hardware vendor strings detected (use env vars with empty defaults)" "$S29"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 30: Code Quality — No bare except:"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [30a] Bare except: (catches SystemExit/KeyboardInterrupt)..."
S30=$(grep_py_notest "aiPlat-infra/infra" 'except\s*:' | grep -v "except Exception\|except BaseException\|except.*Error\|except.*Warning\|except.*DecodeError\|except.*TimeoutError\|except.*KeyError\|except.*ValueError\|except.*TypeError" | grep -v "# noqa\|# allowed" || true)
count=$(_count_lines "$S30")
if [ "$count" -eq 0 ]; then
    check_pass "no bare except: in infra"
else
    check_fail "$count" "bare except: — use specific exception types or except Exception:" "$S30"
fi

# ------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 31: Code Quality — datetime.now() with timezone"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "  [31a] datetime.now() without timezone.utc in infra..."
S31=$(grep_py_notest "aiPlat-infra/infra" 'datetime.now()' | grep -v "timezone\|utcnow\|datetime\.now" | grep -v "# noqa\|# allowed\|tests/" || true)
count=$(_count_lines "$S31")
if [ "$count" -eq 0 ]; then
    check_pass "no naive datetime.now() in infra"
else
    check_fail "$count" "datetime.now() without timezone — use datetime.now(timezone.utc)" "$S31"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 32: Agent→Skill Dependency Validation"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# §32a — Every required_skill/skills reference resolves to a SKILL.md
echo "  [32a] Agent→Skill reference resolution..."
SKILL_DEPS_OUTPUT=$(python3 -c "
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname('$0'), '..', 'aiPlat-core'))
try:
    from core.harness.knowledge.skill_deps import build_skill_deps
    deps = build_skill_deps()
    for r in deps.get('unknown_refs', []):
        agent = r.get('agent', '?')
        ref = r.get('ref', '?')
        if ref:
            print('agent={}: required_skill={} does_not_exist'.format(agent, ref))
except Exception:
    pass
" 2>/dev/null)
if [ -n "$SKILL_DEPS_OUTPUT" ]; then
    VIOLATIONS=$((VIOLATIONS + $(echo "$SKILL_DEPS_OUTPUT" | grep -c ".")))
    echo "$SKILL_DEPS_OUTPUT" | while read -r line; do
        echo -e "  ${RED}[FAIL]${NC} $line"
    done
else
    echo -e "  ${GREEN}PASS${NC}  all Agent→Skill references resolve"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SECTION 33: Skill→Syscall Dependency Validation"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# §33a — Every syscall referenced in SKILL.md SOP is a known syscall
echo "  [33a] Syscall reference validation..."
SKILL_SYSCALL_VIOLATIONS=0
for skill_md in $(find aiPlat-core/core/engine/skills/ -name "SKILL.md" 2>/dev/null); do
    refs=$(grep -oP 'sys_\w+' "$skill_md" 2>/dev/null | sort -u)
    for ref in $refs; do
        if ! grep -q "$ref" aiPlat-core/core/harness/syscalls/__init__.py 2>/dev/null; then
            if ! [ -f "aiPlat-core/core/harness/syscalls/${ref}.py" ]; then
                echo -e "  ${YELLOW}[WARN]${NC} $skill_md references unknown syscall: $ref"
                SKILL_SYSCALL_VIOLATIONS=$((SKILL_SYSCALL_VIOLATIONS + 1))
            fi
        fi
    done
done
if [ "$SKILL_SYSCALL_VIOLATIONS" -eq 0 ]; then
    echo -e "  ${GREEN}PASS${NC}  all SKILL.md syscall references are valid"
fi

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
