#!/bin/bash

set -uo pipefail

echo "=========================================="
echo "概念板块监控状态检查"
echo "=========================================="
echo ""

# 检查API状态
echo "📡 检查API状态..."
STATUS=$(curl -s http://localhost:8000/api/concept-monitor/status || true)
if [ -z "$STATUS" ]; then
    echo "❌ 无法连接 API: http://localhost:8000/api/concept-monitor/status"
    echo "请先启动服务后再检查。"
    echo "=========================================="
    exit 1
fi

# 解析JSON（简单方式）
IS_READY=$(echo $STATUS | grep -o '"is_ready":[^,]*' | cut -d':' -f2)
LAST_UPDATE=$(echo $STATUS | grep -o '"last_update":"[^"]*"' | cut -d'"' -f4)
TOP_TOTAL=$(echo $STATUS | grep -o '"top_concepts_count":[0-9]*' | cut -d':' -f2)
WATCH_TOTAL=$(echo $STATUS | grep -o '"watch_concepts_count":[0-9]*' | cut -d':' -f2)

echo ""
echo "状态信息："
echo "  - 数据就绪: $IS_READY"
echo "  - 最后更新: $LAST_UPDATE"
echo "  - 涨幅榜数量: ${TOP_TOTAL:-0}"
echo "  - 自选榜数量: ${WATCH_TOTAL:-0}"

echo ""
echo "=========================================="

if [ "$IS_READY" == "true" ]; then
    echo "✅ 数据已就绪！可以访问前端查看"
    echo ""
    echo "API端点："
    echo "  - 涨幅前20: http://localhost:8000/api/concept-monitor/top?n=20"
    echo "  - 自选概念: http://localhost:8000/api/concept-monitor/watch"
    echo ""
    echo "前端使用："
    echo "  <ConceptMonitorTable type=\"top\" topN={20} />"
    echo "  <ConceptMonitorTable type=\"watch\" />"
else
    echo "⚠️  数据未就绪，请手动触发一次更新："
    echo "  .venv/bin/python scripts/monitor_no_flask.py --once"
    echo ""
    echo "更新完成后，再运行本脚本确认状态"
fi

echo "=========================================="
