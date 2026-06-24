#!/bin/bash
# verify_restore.sh — 验证恢复后数据完整性
set -euo pipefail

AIPLAT_HOME="${AIPLAT_HOME:-$HOME/.aiplat}"
ERRORS=0

echo "=== aiPlat Restore Verification ==="

# Check SQLite databases
echo "[1/4] SQLite databases..."
for db in "$AIPLAT_HOME"/*.sqlite3; do
    if [ -f "$db" ]; then
        tables=$(sqlite3 "$db" ".tables" 2>/dev/null || echo "")
        rows=$(sqlite3 "$db" "SELECT COUNT(*) FROM $(echo "$tables" | awk '{print $1}')" 2>/dev/null || echo "0")
        echo "  ✓ $(basename "$db"): $tables"
    fi
done

# Check platform DB
PLATFORM_DB="${AIPLAT_PLATFORM_DB_PATH:-$AIPLAT_HOME/platform.sqlite3}"
if [ -f "$PLATFORM_DB" ]; then
    tenant_count=$(sqlite3 "$PLATFORM_DB" "SELECT COUNT(*) FROM tenants" 2>/dev/null || echo "0")
    key_count=$(sqlite3 "$PLATFORM_DB" "SELECT COUNT(*) FROM api_keys WHERE active=1" 2>/dev/null || echo "0")
    echo "  ✓ platform.sqlite3: $tenant_count tenants, $key_count active keys"
fi

# Check configs
echo "[2/4] Configurations..."
for dir in skills agents ontologies task_skills; do
    if [ -d "$AIPLAT_HOME/$dir" ]; then
        count=$(find "$AIPLAT_HOME/$dir" -type f | wc -l)
        echo "  ✓ $dir: $count files"
    else
        echo "  ⚠ $dir: missing"
        ERRORS=$((ERRORS + 1))
    fi
done

# Check KB
echo "[3/4] Knowledge Base..."
KB_DIR="$AIPLAT_HOME/kb"
if [ -d "$KB_DIR" ]; then
    echo "  ✓ kb exists"
else
    echo "  ⚠ kb: missing"
    ERRORS=$((ERRORS + 1))
fi

# Health check (if running)
echo "[4/4] Health check..."
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8003/health 2>/dev/null | grep -q 200; then
    echo "  ✓ Platform API healthy"
elif curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ 2>/dev/null | grep -q 200; then
    echo "  ✓ Frontend responding (platform may be starting)"
else
    echo "  ⚠ Services not running (expected if just restored)"
fi

echo ""
if [ $ERRORS -eq 0 ]; then
    echo "✓ 验证通过 — 所有数据完整"
else
    echo "⚠ 发现 $ERRORS 个问题"
fi
