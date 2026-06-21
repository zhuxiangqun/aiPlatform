#!/bin/bash
# aiplat health — 一键检查所有子系统健康状态
# 用法:  bash scripts/health.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}   aiplat health — 系统健康检查${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

cd "$REPO_ROOT"

# ── 1. Service status ──
echo -e "${CYAN}▶ 服务状态${NC}"
ports=(8002:Core 8000:Management 8003:Platform 8004:App 5173:Frontend)
down=0
for entry in "${ports[@]}"; do
    port="${entry%%:*}"
    name="${entry##*:}"
    if curl -s --max-time 1 "http://localhost:$port" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $name :$port"
    else
        echo -e "  ${RED}✗${NC} $name :$port"
        down=$((down+1))
    fi
done
echo ""

# ── 2. Wiki health ──
echo -e "${CYAN}▶ Wiki 知识库${NC}"
python3 -c "
import sys; sys.path.insert(0,'aiPlat-core')
from core.harness.knowledge.wiki_engine import wiki_health_report, invalidate_graph_cache
invalidate_graph_cache()
r = wiki_health_report()
print(f'  健康分: {r[\"health_score\"]}  |  {r[\"total_pages\"]} pages  |  {len(r[\"issues\"])} issues')
if r['issues']:
    for i in r['issues'][:3]:
        print(f'    - [{i[\"check_type\"]}] {i.get(\"page_a\",\"\")[:30]}')
" 2>/dev/null || echo -e "  ${RED}✗${NC} Python import failed"
echo ""

# ── 3. Capability health ──
echo -e "${CYAN}▶ 能力图谱${NC}"
python3 -c "
import sys; sys.path.insert(0,'aiPlat-core')
for m in list(sys.modules):
    if 'capability' in m or 'cap_health' in m: del sys.modules[m]
from core.harness.knowledge.capability_graph import build_capability_graph, clear_capability_cache
from core.harness.knowledge.capability_health import capability_health_report
clear_capability_cache()
g = build_capability_graph()
r = capability_health_report(g)
print(f'  健康分: {r[\"score\"]} ({r[\"grade\"]})  |  {r[\"signals\"][\"agents\"]} agents  |  {r[\"signals\"][\"skills\"]}/{r[\"signals\"][\"used_skills\"]} skills')
issues = r.get('issues',{})
for k,v in issues.items():
    if v: print(f'    [{k}]: {len(v)}')
" 2>/dev/null || echo -e "  ${RED}✗${NC} Python import failed"
echo ""

# ── 4. Code graph ──
echo -e "${CYAN}▶ 代码图谱${NC}"
python3 -c "
import sys; sys.path.insert(0,'aiPlat-core')
from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root
from pathlib import Path
root = repo_root()
roots = [(root / r).resolve() for r in default_roots()]
nodes, edges, issues = build_graph(root, roots)
repos = {}
for p in nodes:
    r = p.split('/')[0]
    repos[r] = repos.get(r,0)+1
print(f'  {len(nodes)} files  |  {len(edges)} edges  |  {len(issues)} issues')
for r,c in sorted(repos.items()):
    print(f'    {r}: {c} files')
" 2>/dev/null || echo -e "  ${RED}✗${NC} Python import failed"
echo ""

# ── 5. Architecture guard ──
echo -e "${CYAN}▶ 架构守卫${NC}"
bash scripts/architecture_guard.sh 2>&1 | tail -3 | while IFS= read -r line; do
    line_clean=$(echo "$line" | sed 's/\x1B\[[0-9;]*m//g')
    if echo "$line_clean" | grep -q "PASSED"; then
        echo -e "  ${GREEN}✓${NC} ${line_clean##*═══ }"
    elif echo "$line_clean" | grep -q "FAILED"; then
        echo -e "  ${RED}✗${NC} ${line_clean##*═══ }"
    fi
done
echo ""

# ── Summary ──
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ $down -eq 0 ]; then
    echo -e "  ${GREEN}所有服务运行中${NC}  |  ${GREEN}架构守卫通过${NC}"
else
    echo -e "  ${YELLOW}$down 个服务未启动${NC}  |  启动: ${GREEN}bash scripts/dev.sh${NC}"
fi
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
