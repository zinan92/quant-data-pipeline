#!/bin/bash

# ashare 一键启动脚本 - 彻底解决服务中断问题
# 使用 nohup 确保服务不被意外中断

echo "🚀 启动 ashare 全套服务..."

# 停止现有服务
echo "🛑 停止现有服务..."
pkill -f "uvicorn web.app:app"
pkill -f "vite"
sleep 2

# 确保目录存在
cd /Users/wendy/ashare || exit 1

# 启动后端服务 (使用 nohup 防止被中断)
echo "🔧 启动后端服务 (端口 8000)..."
nohup /Users/wendy/ashare/.venv/bin/python -m uvicorn web.app:app --port 8000 --host 127.0.0.1 > logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "后端 PID: $BACKEND_PID"

# 等待后端启动
sleep 3

# 检查后端是否启动成功
if curl -s http://localhost:8000/docs > /dev/null; then
    echo "✅ 后端服务启动成功"
else
    echo "❌ 后端服务启动失败"
    exit 1
fi

# 启动前端服务 (使用 nohup 防止被中断)
echo "🎨 启动前端服务 (端口 5173)..."
cd frontend
nohup npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "前端 PID: $FRONTEND_PID"

# 等待前端启动
sleep 3

# 检查前端是否启动成功
if curl -s http://localhost:5173 > /dev/null; then
    echo "✅ 前端服务启动成功"
else
    echo "❌ 前端服务启动失败"
fi

echo ""
echo "🎉 ashare 服务启动完成！"
echo "📊 后端: http://localhost:8000"
echo "🌐 前端: http://localhost:5173"
echo "📝 后端日志: logs/backend.log"
echo "📝 前端日志: logs/frontend.log"
echo ""
echo "进程ID:"
echo "后端: $BACKEND_PID"
echo "前端: $FRONTEND_PID"