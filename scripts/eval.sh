#!/bin/bash
# aiplat eval — 命令行运行 Agent 评估
# 用法:
#   bash scripts/eval.sh                      → 查看概览
#   bash scripts/eval.sh sets                 → 列出评估集
#   bash scripts/eval.sh run <set_id>         → 运行评估 (dry run)
#   bash scripts/eval.sh run <set_id> --live  → 运行评估 (真实执行)
#   bash scripts/eval.sh score <agent_id>     → 查看 Agent 评分

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

cd "$REPO_ROOT"

case "${1:-overview}" in
  overview)
    echo -e "${CYAN}═══ Agent 运行评估概览 ═══${NC}"
    python3 -c "
import sys; sys.path.insert(0,'aiPlat-core')
from core.harness.evaluation.eval_runner import list_eval_sets
import json, os
from pathlib import Path
sets = list_eval_sets()
results_dir = Path(os.getenv('AIPLAT_HOME', os.path.expanduser('~/.aiplat'))) / 'eval_results'
results = list(results_dir.glob('*.json'))
print(f'评估集: {len(sets)}')
print(f'评估记录: {len(results)}')
print()
print('评估集列表:')
for s in sets:
    print(f'  {s[\"set_id\"]:30s} {s[\"category\"]:15s} {s[\"tasks\"]} tasks — {s[\"description\"]}')
if results:
    print()
    print('最近评估:')
    for r in sorted(results, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
        try:
            d = json.loads(r.read_text())
            aid = d.get('agent_id','?')
            score = d.get('composite_score','?')
            g = d.get('grade','?')
            tasks = d.get('total_tasks','?')
            print(f'  {aid:20s} score={score} ({g})  {tasks} tasks')
        except: pass
"
    ;;

  sets)
    python3 -c "
import sys; sys.path.insert(0,'aiPlat-core')
from core.harness.evaluation.eval_runner import list_eval_sets, load_eval_set
sets = list_eval_sets()
for s in sets:
    es = load_eval_set(s['set_id'])
    print(f'\\n{s[\"set_id\"]} ({s[\"category\"]})')
    print(f'  {s[\"description\"]}')
    if es:
        for t in es.tasks:
            print(f'  [{t.category}] {t.agent_id}: {t.user_input[:60]}...')
"
    ;;

  run)
    set_id="${2:-}"
    if [ -z "$set_id" ]; then
      echo "用法: bash scripts/eval.sh run <set_id> [--live]"
      echo "       bash scripts/eval.sh sets  (先看有哪些评估集)"
      exit 1
    fi
    dry_run="true"
    if [ "${3:-}" = "--live" ]; then
      dry_run="false"
    fi
    
    if [ "$dry_run" = "true" ]; then
      echo -e "${YELLOW}Dry run mode — 验证评估集，不执行 Agent${NC}"
      echo ""

      python3 -c "
import sys, asyncio; sys.path.insert(0,'aiPlat-core')
from core.harness.evaluation.eval_runner import load_eval_set, EvalRunner

async def main():
    es = load_eval_set('$set_id')
    if not es:
        print(f'❌ 评估集 \"$set_id\" 不存在')
        return
    runner = EvalRunner()
    result = await runner.run_eval_set(es, dry_run=True)
    print(f'评估集: {es.set_id} ({es.category}) — {es.description}')
    print(f'任务数: {result.total_tasks}')
    for tr in result.task_results:
        print(f'  [{tr.task_id}] {tr.agent_id}: {tr.reasoning}')

asyncio.run(main())
"
    else
      echo -e "${GREEN}Live mode — 真实执行 Agent${NC}"
      echo "确保 core 服务已启动: bash scripts/dev.sh core"
      echo ""
      echo "正在执行评估..."

      python3 -c "
import sys, asyncio; sys.path.insert(0,'aiPlat-core')
from core.harness.evaluation.eval_runner import load_eval_set, EvalRunner

async def main():
    es = load_eval_set('$set_id')
    if not es:
        print(f'❌ 评估集 \"$set_id\" 不存在')
        return
    runner = EvalRunner()
    result = await runner.run_eval_set(es, dry_run=False)
    print(f'\\n═══ 评估结果 ═══')
    print(f'Agent: {result.agent_id}')
    print(f'综合分: {result.composite_score:.1f} ({result.grade})')
    print(f'任务完成: {result.task_completion.complete_count}/{result.total_tasks} complete')
    print(f'可靠性: {result.task_completion.reliability_rate:.0%}')
    print(f'工具质量: {result.tool_quality.overall_score:.2f}')
    print(f'安全: 违规={result.safety.high_risk_pre_confirm_violations}')
    print(f'\\n详细:')
    for tr in result.task_results:
        icon = {'complete':'✅','partial':'⚠️','correct_failure':'🛑','error_failure':'❌'}.get(tr.level.value,'?')
        print(f'  {icon} [{tr.task_id}] {tr.agent_id}: {tr.reasoning[:80]}')

asyncio.run(main())
"
    fi
    ;;

  score)
    agent_id="${2:-}"
    if [ -z "$agent_id" ]; then
      echo "用法: bash scripts/eval.sh score <agent_id>"
      exit 1
    fi
    python3 -c "
import sys; sys.path.insert(0,'aiPlat-core')
from core.harness.evaluation.eval_runner import _load_results
results = _load_results('$agent_id')
if not results:
    print(f'Agent \"$agent_id\" 暂无评估数据')
else:
    r = results[0]
    print(f'Agent: $agent_id')
    print(f'综合分: {r.get(\"composite_score\",\"?\")} ({r.get(\"grade\",\"?\")})')
    print(f'任务完成: {r.get(\"task_completion\",{}).get(\"complete\",\"?\")}/{r.get(\"total_tasks\",\"?\")}')
    print(f'可靠性: {r.get(\"task_completion\",{}).get(\"reliability\",\"?\")}%')
    print(f'安全违规: {r.get(\"safety\",{}).get(\"violations\",\"?\")}')
    print(f'评估次数: {len(results)}')
"
    ;;

  *)
    echo "用法: bash scripts/eval.sh {overview|sets|run|score}"
    echo ""
    echo "  overview    查看评估概览"
    echo "  sets        列出所有评估集"
    echo "  run <id>    运行评估 (dry run 验证)"
    echo "  run <id> --live  运行评估 (真实执行)"
    echo "  score <id>  查看 Agent 评分"
    ;;
esac
