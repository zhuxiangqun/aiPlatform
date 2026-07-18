#!/bin/bash
# FDE 安全行前检查脚本（§1.4 引用）
# 用途：进入步骤①前执行，确认本地环境已满足安全要求

set -e

FW_DIR="$HOME/fde_workspace"

echo "🔐 FDE 安全行前检查"
echo "===================="

# ── 1. 检查 fde_workspace 目录 ──
if [ ! -d "$FW_DIR" ]; then
    echo "⚠️  $FW_DIR 不存在，正在创建..."
    mkdir -p "$FW_DIR"
    chmod 700 "$FW_DIR"
    echo "✅ $FW_DIR 已创建，权限 700"
else
    echo "✅ $FW_DIR 已就绪"
fi

# ── 2. 检查脱敏脚本是否可执行 ──
SANITIZE_SCRIPT="$(dirname "$0")/sanitize_logs.sh"
if [ ! -f "$SANITIZE_SCRIPT" ]; then
    echo "❌ $SANITIZE_SCRIPT 不存在"
    echo "   请确认 sanitize_logs.sh 与 security_preflight.sh 在同一目录"
    exit 1
fi
if [ ! -x "$SANITIZE_SCRIPT" ]; then
    echo "⚠️  $SANITIZE_SCRIPT 不可执行，正在设置权限..."
    chmod +x "$SANITIZE_SCRIPT"
fi
echo "✅ sanitize_logs.sh 可执行"

# ── 3. 检查是否有未脱敏的日志残留 ──
LOG_DIR="./logs"
if [ -d "$LOG_DIR" ]; then
    RAW_COUNT=$(find "$LOG_DIR" -name "*.log" -newer "$FW_DIR/.last_sanitized" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$RAW_COUNT" -gt 0 ]; then
        echo "⚠️  检测到 $RAW_COUNT 个日志文件可能未脱敏"
        echo "   请在离场前运行: bash scripts/sanitize_logs.sh"
    else
        echo "✅ 日志文件已脱敏"
    fi
else
    echo "✅ 无日志目录"
fi

# ── 4. 检查临时账号标记 ──
TEMP_ACCT="$FW_DIR/.temp_accounts"
if [ -f "$TEMP_ACCT" ]; then
    echo "⚠️  检测到临时账号记录: $TEMP_ACCT"
    echo "   离场前请确保所有临时账号已注销"
else
    echo "✅ 无临时账号记录"
fi

echo ""
echo "✅ 所有安全策略已生效"
exit 0
