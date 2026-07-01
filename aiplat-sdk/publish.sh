#!/usr/bin/env bash
# publish.sh — 构建并发布 aiplat-sdk 到 PyPI
#
# 用法:
#   bash aiplat-sdk/publish.sh [--test]
#   --test  发布到 TestPyPI (https://test.pypi.org)
#   (默认)  发布到 PyPI (https://pypi.org)
#
# 前置条件:
#   pip install build twine
#   PyPI 凭据: 设置 TWINE_USERNAME 和 TWINE_PASSWORD 环境变量
#   或使用 ~/.pypirc 配置文件
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

TEST_MODE=false
if [ "${1:-}" = "--test" ]; then
    TEST_MODE=true
fi

echo "=== 1. 清理旧构建 ==="
rm -rf dist/ build/ *.egg-info/

echo "=== 2. 构建包 ==="
python3 -m build --wheel --sdist

echo "=== 3. 检查包 ==="
python3 -m twine check dist/*

echo "=== 4. 上传 ==="
if [ "$TEST_MODE" = true ]; then
    echo "→ 发布到 TestPyPI"
    python3 -m twine upload --repository testpypi dist/*
    echo ""
    echo "安装测试: pip install -i https://test.pypi.org/simple/ aiplat-sdk"
else
    echo "→ 发布到 PyPI"
    echo "确认发布到生产 PyPI? (y/N)"
    read -r confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "已取消"
        exit 0
    fi
    python3 -m twine upload dist/*
    echo ""
    echo "安装: pip install aiplat-sdk"
fi

echo "=== 完成 ==="
