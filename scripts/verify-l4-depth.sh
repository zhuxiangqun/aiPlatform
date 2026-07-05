#!/usr/bin/env bash
# verify-l4-depth.sh — L5 能力深度验证 (Python 测试套件)
# 
# Unlike verify-l4-pyramid.sh (grep-based existence),
# this script runs actual Python unit tests that exercise module logic.
#
# Tests verify:
#   F轴: UCB1 convergence under biased data
#   A轴: GoalExecutor stats + debounce
#   C轴: ToolBootstrap skill generation + registration
#   E轴: DynamicOrchestrator capability gap detection
#   D轴: SharedKnowledgePool cross-session query + isolation
#   集成: Tracker → SearchEngine data flow

set -euo pipefail

CORE="$(cd "$(dirname "$0")/../aiPlat-core" && pwd)"

echo "========================================="
echo " L5 能力深度验证"
echo " 验证模块不只是存在, 而是真正在工作"
echo "========================================="
echo ""

cd "$CORE"
python -m pytest tests/autonomy/test_l5_capabilities.py -v --tb=short -q 2>&1

EXIT=$?
echo ""
if [ $EXIT -eq 0 ]; then
    echo "✅ L5 能力深度验证通过 (96/96)"
else
    echo "❌ L5 能力深度验证失败"
fi
exit $EXIT
