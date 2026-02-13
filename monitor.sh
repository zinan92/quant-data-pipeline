#!/bin/bash

# ashare 服务监控脚本 - 自动检测并重启失效的服务

check_service() {
    local port=$1
    local name=$2
    
    if curl -s "http://localhost:$port" > /dev/null; then
        echo "✅ $name (端口 $port) 正常"
        return 0
    else
        echo "❌ $name (端口 $port) 异常"
        return 1
    fi
}

echo "🔍 检查 ashare 服务状态..."

# 检查后端服务
if ! check_service 8000 "后端API"; then
    echo "🔧 重启后端服务..."
    pkill -f "uvicorn web.app:app"
    cd /Users/wendy/ashare
    nohup /Users/wendy/ashare/.venv/bin/python -m uvicorn web.app:app --port 8000 --host 127.0.0.1 > logs/backend.log 2>&1 &
    sleep 3
fi

# 检查前端服务  
if ! check_service 5173 "前端界面"; then
    echo "🔧 重启前端服务..."
    pkill -f "vite"
    cd /Users/wendy/ashare/frontend
    nohup npm run dev > ../logs/frontend.log 2>&1 &
    sleep 3
fi

echo "📊 最终状态:"
check_service 8000 "后端API"
check_service 5173 "前端界面"

echo "🕒 $(date) - 监控检查完成"