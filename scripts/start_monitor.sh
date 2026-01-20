#!/bin/bash

echo "=================================="
echo "板块监控API服务启动脚本"
echo "=================================="

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3"
    exit 1
fi

# 安装依赖
echo "📦 检查依赖..."
pip3 install -q -r scripts/requirements.txt

# 启动服务
echo "🚀 启动API服务..."
echo ""
python3 scripts/api_server.py
