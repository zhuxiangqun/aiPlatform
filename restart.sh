#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  aiPlat-platform - 重启服务"
echo "============================================================"

./stop.sh
sleep 1
./start.sh

