#!/bin/bash
# 日志脱敏脚本（§1.4 引用）
# 用途：在采集日志带离客户现场前，替换 IP、邮箱、中文姓名为 [REDACTED]
# 用法：bash scripts/sanitize_logs.sh [日志目录，默认 ./logs]

set -e

LOG_DIR="${1:-./logs}"

if [ ! -d "$LOG_DIR" ]; then
    echo "⚠️  日志目录 $LOG_DIR 不存在，跳过"
    exit 0
fi

FILE_COUNT=$(find "$LOG_DIR" -type f -name "*.log" | wc -l | tr -d ' ')
if [ "$FILE_COUNT" -eq 0 ]; then
    echo "✅ $LOG_DIR 中无日志文件，跳过"
    exit 0
fi

echo "🛡️  开始脱敏 $LOG_DIR（$FILE_COUNT 个文件）..."

find "$LOG_DIR" -type f -name "*.log" | while read -r file; do
    echo "  处理: $(basename "$file")"
    # 替换 IPv4 地址
    perl -i -CSD -pe 's/\b([0-9]{1,3}\.){3}[0-9]{1,3}\b/[REDACTED_IP]/g' "$file" 2>/dev/null || \
    sed -i '' -E 's/[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[REDACTED_IP]/g' "$file"

    # 替换邮箱
    perl -i -CSD -pe 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/[REDACTED_EMAIL]/g' "$file" 2>/dev/null || \
    sed -i '' -E 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/[REDACTED_EMAIL]/g' "$file"

    # 替换中文姓名模式（2-3个中文字符 + 括号内职务）
    perl -i -CSD -pe 's/[\x{4e00}-\x{9fa5}]{2,3}（[^）]*）/[REDACTED_NAME]/g' "$file" 2>/dev/null || true
done

# 记录脱敏时间戳
mkdir -p "$HOME/fde_workspace"
date '+%Y-%m-%d %H:%M:%S' > "$HOME/fde_workspace/.last_sanitized"

echo "✅ 脱敏完成（时间戳已记录）"
