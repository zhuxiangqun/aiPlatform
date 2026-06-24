#!/bin/bash
# restore.sh — aiPlat 数据恢复
# 用法: bash scripts/ops/restore.sh 20260624_120000 [--dry-run]
set -euo pipefail

BACKUP_ID="${1:-}"
if [ -z "$BACKUP_ID" ]; then
    echo "用法: bash scripts/ops/restore.sh <backup_id> [--dry-run]"
    echo "可用备份:"
    ls -1 "${AIPLAT_BACKUP_DIR:-$HOME/.aiplat/backups}/" 2>/dev/null || echo "  (无)"
    exit 1
fi

DRY_RUN=false
if [ "${2:-}" = "--dry-run" ]; then
    DRY_RUN=true
fi

AIPLAT_HOME="${AIPLAT_HOME:-$HOME/.aiplat}"
BACKUP_PATH="${AIPLAT_BACKUP_DIR:-$AIPLAT_HOME/backups}/$BACKUP_ID"

if [ ! -d "$BACKUP_PATH" ]; then
    echo "❌ 备份不存在: $BACKUP_PATH"
    exit 1
fi

if $DRY_RUN; then
    echo "=== DRY RUN === (不会实际修改数据)"
fi

echo "=== aiPlat Restore: $BACKUP_ID ==="

# 1. Stop services
if ! $DRY_RUN; then
    echo "[1/5] 停止服务..."
    "$(dirname "$0")/../../stop.sh" 2>/dev/null || true
    sleep 2
fi

# 2. Restore SQLite databases
echo "[2/5] 恢复 SQLite 数据库..."
for db in "$BACKUP_PATH"/*.sqlite3; do
    if [ -f "$db" ]; then
        dbname="$(basename "$db")"
        if ! $DRY_RUN; then
            cp "$db" "$AIPLAT_HOME/$dbname"
        fi
        echo "  ✓ $dbname"
    fi
done

# 3. Restore configs
echo "[3/5] 恢复配置文件..."
if [ -f "$BACKUP_PATH/configs.tar.gz" ]; then
    if ! $DRY_RUN; then
        tar -xzf "$BACKUP_PATH/configs.tar.gz" -C / 2>/dev/null
    fi
    echo "  ✓ configs restored"
fi

# 4. Restore KB
echo "[4/5] 恢复知识库..."
if [ -f "$BACKUP_PATH/kb.tar.gz" ]; then
    if ! $DRY_RUN; then
        tar -xzf "$BACKUP_PATH/kb.tar.gz" -C "$AIPLAT_HOME" 2>/dev/null
    fi
    echo "  ✓ KB restored"
fi

# 5. Restore execution data
echo "[5/5] 恢复执行数据..."
REPO_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
if [ -f "$BACKUP_PATH/execution_data.tar.gz" ]; then
    if ! $DRY_RUN; then
        tar -xzf "$BACKUP_PATH/execution_data.tar.gz" -C "$REPO_ROOT/aiPlat-core/core" 2>/dev/null
    fi
    echo "  ✓ Execution data restored"
fi

if ! $DRY_RUN; then
    echo ""
    echo "✓ 恢复完成"
    echo "  运行 bash scripts/ops/verify_restore.sh $BACKUP_ID 验证数据完整性"
    echo "  运行 bash start.sh 重启服务"
else
    echo ""
    echo "✓ DRY RUN 完成 (未实际修改数据)"
fi
