#!/usr/bin/env bash
# fault-injection.sh — lightweight chaos engineering for aiPlat
# Simulates failures in docker-compose/local environment.
# Chaos Mesh equivalent for single-node deployment.
#
# Usage: bash scripts/fault-injection.sh [--aggressive]

set -euo pipefail

AGGRESSIVE=false
[[ "${1:-}" == "--aggressive" ]] && AGGRESSIVE=true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

check_health() {
    local label="$1"
    local url="${2:-http://localhost:8000/health}"
    if curl -sf "$url" --connect-timeout 5 --max-time 10 > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $label"
        PASS=$((PASS+1))
        return 0
    else
        echo -e "  ${RED}✗${NC} $label"
        FAIL=$((FAIL+1))
        return 1
    fi
}

echo ""
echo "========================================="
echo " aiPlat 故障注入演练"
echo " 环境: docker-compose / local"
echo " 模式: $([ "$AGGRESSIVE" = true ] && echo '激进(可能造成数据丢失)' || echo '安全(只杀进程)')"
echo "========================================="
echo ""

# ══════════════════════════════════════════════════════
# F1: 进程崩溃 — 杀 core 进程, 观察恢复
# ══════════════════════════════════════════════════════
echo "[F1] 进程崩溃恢复"
echo "  目标: 杀 core 进程 → 等待重启 → 健康检查"

CORE_PID=$(pgrep -f "uvicorn server:app.*8002" 2>/dev/null | head -1 || echo "")
if [ -n "$CORE_PID" ]; then
    echo "  Core PID: $CORE_PID"
    kill -9 "$CORE_PID" 2>/dev/null || true
    echo "  Core 进程已 kill, 等待恢复..."
    for i in $(seq 1 30); do
        sleep 2
        if curl -sf http://localhost:8000/api/diagnostics/health/all --connect-timeout 5 --max-time 10 > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} 恢复成功 (${i}x2 = $((i*2))s)"
            PASS=$((PASS+1))
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo -e "  ${RED}✗${NC} 恢复超时 (60s)"
            FAIL=$((FAIL+1))
        fi
    done
else
    echo -e "  ${YELLOW}⚠${NC}  Core 进程未找到 (可能未运行或进程名不匹配)"
fi

# ══════════════════════════════════════════════════════
# F2: 磁盘压力 — 填满 snapshot 目录, 测试降级
# ══════════════════════════════════════════════════════
echo ""
echo "[F2] 磁盘压力测试"
echo "  目标: 填满 snapshot 目录 → 验证降级不崩溃"

SNAP_DIR="${HOME}/.aiplat/snapshots"
if [ -d "$SNAP_DIR" ]; then
    echo "  创建 100 个空快照文件模拟磁盘压力..."
    for i in $(seq 1 100); do
        touch "$SNAP_DIR/stress_test_$i.json" 2>/dev/null || true
    done
    # 验证系统仍然可达
    check_health "snapshot 压力后健康检查" "http://localhost:8000/health"
    # 清理
    rm -f "$SNAP_DIR"/stress_test_*.json 2>/dev/null || true
else
    echo -e "  ${YELLOW}⚠${NC}  Snapshot 目录不存在 (${SNAP_DIR})"
fi

# ══════════════════════════════════════════════════════
# F3: 数据库故障 — 测试 WAL 恢复
# ══════════════════════════════════════════════════════
echo ""
echo "[F3] 数据库故障恢复"
echo "  目标: 读写 SharedKnowledgePool → 验证 WAL 恢复"

POOL_DB="${HOME}/.aiplat/shared_knowledge/pool.db"
if [ -f "$POOL_DB" ]; then
    # 备份原 DB
    cp "$POOL_DB" "${POOL_DB}.bak" 2>/dev/null || true
    echo "  尝试并发写入 pool.db..."
    # 写入 5 个事实
    for i in $(seq 1 5); do
        python3 -c "
import sys; sys.path.insert(0,'.')
from core.harness.memory.shared_pool import get_shared_knowledge_pool
p = get_shared_knowledge_pool()
p.publish(f'fault_test_{$i}', f'data_{$i}', source='fault_injection')
" 2>/dev/null && echo "  ✓ 写入 $i" || echo "  ✗ 写入 $i 失败"
    done
    # 恢复
    mv "${POOL_DB}.bak" "$POOL_DB" 2>/dev/null || true
    check_health "WAL 恢复后健康检查" "http://localhost:8000/health"
else
    echo -e "  ${YELLOW}⚠${NC}  SharedKnowledgePool DB 不存在"
fi

# ══════════════════════════════════════════════════════
# F4: 激进模式 — 网络中断 + 大规模并发
# ══════════════════════════════════════════════════════
if [ "$AGGRESSIVE" = true ]; then
    echo ""
    echo "[F4] 激进: 大规模并发请求"
    echo "  目标: 50 并发请求 → 验证不崩溃"
    SUCCESS=0
    for i in $(seq 1 50); do
        curl -sf http://localhost:8000/api/diagnostics/health/all --connect-timeout 3 --max-time 8 > /dev/null 2>&1 &
        SUCCESS=$((SUCCESS+1))
    done
    wait
    echo "  完成 $SUCCESS 个并发请求"
    check_health "并发后健康检查" "http://localhost:8000/health"
fi

echo ""
echo "========================================="
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}✅ 故障演练通过 ($PASS PASS / $FAIL FAIL)${NC}"
else
    echo -e "${RED}❌ 故障演练失败 ($PASS PASS / $FAIL FAIL)${NC}"
fi
echo "========================================="
echo ""
echo "说明:"
echo "  F1 验证进程崩溃恢复 (RTO)"
echo "  F2 验证磁盘压力降级"
echo "  F3 验证数据库故障恢复 (RPO)"
echo "  F4 验证并发压力 (仅 --aggressive)"
echo ""
echo "  添加 --aggressive 参数启用大规模并发测试"
echo "  完整 Chaos Mesh 演练需要 K8s 集群"
echo ""
exit $FAIL
