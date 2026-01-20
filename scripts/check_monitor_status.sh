#!/bin/bash

echo "=========================================="
echo "概念板块监控状态检查"
echo "=========================================="
echo ""

# 检查API状态
echo "📡 检查API状态..."
STATUS=$(curl -s http://localhost:8000/api/concept-monitor/status)

# 解析JSON（简单方式）
IS_READY=$(echo $STATUS | grep -o '"is_ready":[^,]*' | cut -d':' -f2)
IS_UPDATING=$(echo $STATUS | grep -o '"is_updating":[^,]*' | cut -d':' -f2)
LAST_UPDATE=$(echo $STATUS | grep -o '"last_update":"[^"]*"' | cut -d'"' -f4)
TOTAL=$(echo $STATUS | grep -o '"total_concepts":[0-9]*' | cut -d':' -f2)

echo ""
echo "状态信息："
echo "  - 数据就绪: $IS_READY"
echo "  - 正在更新: $IS_UPDATING"
echo "  - 最后更新: $LAST_UPDATE"
echo "  - 板块总数: $TOTAL"

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
elif [ "$IS_UPDATING" == "true" ]; then
    echo "⏳ 正在更新中...（预计5-10分钟）"
    echo ""
    echo "可以运行以下命令查看进度："
    echo "  watch -n 5 $0"
else
    echo "⚠️  数据未就绪，触发更新..."
    curl -X POST http://localhost:8000/api/concept-monitor/refresh
    echo ""
    echo "更新已触发，请等待5-10分钟"
fi

echo "=========================================="
