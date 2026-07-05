#!/usr/bin/env bash
# notify-release.sh — send deployment notification via webhook
# Supports: Slack, Feishu, custom webhook
# Usage: bash scripts/notify-release.sh [status] [message]
set -euo pipefail

STATUS="${1:-deployed}"
MSG="${2:-aiPlat $STATUS at $(date -u +%Y-%m-%dT%H:%M:%SZ)}"
VERSION="${GITHUB_SHA:-$(git rev-parse HEAD 2>/dev/null || echo 'unknown')}"
VERSION_SHORT="${VERSION:0:8}"

# Slack webhook
if [ -n "${AIPLAT_SLACK_WEBHOOK:-}" ]; then
    curl -s -X POST "$AIPLAT_SLACK_WEBHOOK" \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"aiPlat $STATUS: $MSG\nVersion: \`$VERSION_SHORT\`\nTime: $(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
fi

# Feishu webhook
if [ -n "${AIPLAT_FEISHU_WEBHOOK:-}" ]; then
    curl -s -X POST "$AIPLAT_FEISHU_WEBHOOK" \
        -H "Content-Type: application/json" \
        -d "{\"msg_type\": \"text\", \"content\": {\"text\": \"aiPlat $STATUS: $MSG\nVersion: $VERSION_SHORT\"}}"
fi

# Generic webhook
if [ -n "${AIPLAT_DEPLOY_WEBHOOK:-}" ]; then
    curl -s -X POST "$AIPLAT_DEPLOY_WEBHOOK" \
        -H "Content-Type: application/json" \
        -d "{\"status\": \"$STATUS\", \"message\": \"$MSG\", \"version\": \"$VERSION_SHORT\"}"
fi

echo "Release notification sent ($STATUS)"
