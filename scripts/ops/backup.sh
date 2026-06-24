#!/bin/bash
# backup.sh — aiPlat 全量备份
# 用法: bash scripts/ops/backup.sh [--s3]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
AIPLAT_HOME="${AIPLAT_HOME:-$HOME/.aiplat}"
BACKUP_DIR="${AIPLAT_BACKUP_DIR:-$AIPLAT_HOME/backups}"
DATE="$(date +%Y%m%d_%H%M%S)"
BACKUP_PATH="$BACKUP_DIR/$DATE"

mkdir -p "$BACKUP_PATH"

echo "=== aiPlat Backup: $DATE ==="

# 1. SQLite databases
echo "[1/5] SQLite databases..."
for db in "$AIPLAT_HOME"/*.sqlite3; do
    if [ -f "$db" ]; then
        cp "$db" "$BACKUP_PATH/$(basename "$db")"
        echo "  ✓ $(basename "$db") ($(du -h "$db" | cut -f1))"
    fi
done

# Platform SQLite
PLATFORM_DB="${AIPLAT_PLATFORM_DB_PATH:-$AIPLAT_HOME/platform.sqlite3}"
if [ -f "$PLATFORM_DB" ]; then
    cp "$PLATFORM_DB" "$BACKUP_PATH/platform.sqlite3"
    echo "  ✓ platform.sqlite3 ($(du -h "$PLATFORM_DB" | cut -f1))"
fi

# 2. Configuration files
echo "[2/5] Skills, Agents, Ontologies..."
CONFIG_FILES=()
for dir in "$AIPLAT_HOME/skills" "$AIPLAT_HOME/agents" "$AIPLAT_HOME/ontologies" "$AIPLAT_HOME/task_skills"; do
    if [ -d "$dir" ]; then
        CONFIG_FILES+=("$dir")
    fi
done
if [ ${#CONFIG_FILES[@]} -gt 0 ]; then
    tar -czf "$BACKUP_PATH/configs.tar.gz" "${CONFIG_FILES[@]}" 2>/dev/null
    echo "  ✓ configs.tar.gz ($(du -h "$BACKUP_PATH/configs.tar.gz" | cut -f1))"
fi

# 3. Knowledge Base data
echo "[3/5] Knowledge Base..."
KB_DIR="$AIPLAT_HOME/kb"
if [ -d "$KB_DIR" ]; then
    tar -czf "$BACKUP_PATH/kb.tar.gz" -C "$AIPLAT_HOME" kb/ 2>/dev/null
    echo "  ✓ kb.tar.gz ($(du -h "$BACKUP_PATH/kb.tar.gz" | cut -f1))"
fi

# 4. Execution data
echo "[4/5] Execution data..."
EXEC_DIR="$REPO_ROOT/aiPlat-core/core/data"
if [ -d "$EXEC_DIR" ]; then
    tar -czf "$BACKUP_PATH/execution_data.tar.gz" -C "$REPO_ROOT/aiPlat-core/core" data/ 2>/dev/null
    echo "  ✓ execution_data.tar.gz ($(du -h "$BACKUP_PATH/execution_data.tar.gz" | cut -f1))"
fi

# 5. Upload to S3/MinIO (optional)
if [ "${1:-}" = "--s3" ] && [ -n "${AIPLAT_BACKUP_S3_URL:-}" ]; then
    echo "[5/5] Uploading to S3..."
    if command -v aws &>/dev/null; then
        aws s3 cp --recursive "$BACKUP_PATH" "$AIPLAT_BACKUP_S3_URL/$DATE/" --quiet
        echo "  ✓ Uploaded to $AIPLAT_BACKUP_S3_URL/$DATE/"
    else
        echo "  ⚠ aws CLI not found, skipping S3 upload"
    fi
else
    echo "[5/5] S3 upload skipped (use --s3 and set AIPLAT_BACKUP_S3_URL)"
fi

# Cleanup old backups (>30 days)
find "$BACKUP_DIR" -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \; 2>/dev/null || true

echo ""
echo "✓ Backup complete: $BACKUP_PATH"
echo "  Restore: bash scripts/ops/restore.sh $DATE"
