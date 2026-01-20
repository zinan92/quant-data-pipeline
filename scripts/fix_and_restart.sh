#!/bin/bash

echo "=========================================="
echo "🔧 修复概念板块监控系统"
echo "=========================================="
echo ""

# 1. 停止被阻塞的FastAPI
echo "1️⃣ 停止当前FastAPI进程..."
pkill -f "uvicorn web.app"
sleep 2

# 2. 先生成一次数据（单次模式，不阻塞）
echo ""
echo "2️⃣ 生成初始数据（单次模式）..."
echo "   这将需要5-10分钟，请耐心等待..."
cd /Users/park/a-share-data
python3 scripts/monitor_no_flask.py --once

# 3. 重启FastAPI
echo ""
echo "3️⃣ 重启FastAPI服务..."
cd /Users/park/a-share-data
nohup uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload > logs/fastapi.log 2>&1 &

sleep 3

# 4. 测试API
echo ""
echo "4️⃣ 测试API..."
curl -s http://localhost:8000/api/concept-monitor/status | python3 -m json.tool

echo ""
echo "=========================================="
echo "✅ 修复完成！"
echo ""
echo "后续步骤："
echo "1. 如需持续监控，运行："
echo "   nohup python3 scripts/monitor_no_flask.py > logs/monitor.log 2>&1 &"
echo ""
echo "2. 查看FastAPI日志："
echo "   tail -f logs/fastapi.log"
echo ""
echo "3. 查看监控日志："
echo "   tail -f logs/monitor.log"
echo "=========================================="
