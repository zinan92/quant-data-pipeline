#!/bin/bash
# 监控股票下载进度

LOG_FILE="logs/populate_all_stocks.log"
INTERVAL=300  # 每5分钟检查一次

echo "========================================"
echo "股票下载进度监控"
echo "========================================"
echo "日志文件: $LOG_FILE"
echo "检查间隔: ${INTERVAL}秒 ($(($INTERVAL / 60))分钟)"
echo ""

while true; do
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="

    # 检查脚本是否还在运行
    if ps aux | grep -v grep | grep "populate_all_stocks.py" > /dev/null; then
        echo "✅ 脚本运行中"
    else
        echo "⚠️  脚本已停止"
    fi

    # 检查数据库股票数量
    stock_count=$(python3 -c "
from src.database import session_scope
from src.models import SymbolMetadata
with session_scope() as session:
    print(session.query(SymbolMetadata).count())
" 2>/dev/null)

    echo "📊 数据库股票数: ${stock_count:-未知}"

    # 显示最新进度
    echo ""
    echo "📝 最新进度:"
    tail -100 "$LOG_FILE" 2>/dev/null | grep -E "^\s+\[|⚠️|暂停60秒" | tail -5

    # 检查是否有错误
    recent_errors=$(tail -200 "$LOG_FILE" 2>/dev/null | grep -c "Connection aborted")
    if [ "$recent_errors" -gt 0 ]; then
        echo ""
        echo "⚠️  最近200行日志中有 $recent_errors 个连接错误"
    fi

    echo ""
    echo "下次检查: $(date -v+${INTERVAL}S '+%Y-%m-%d %H:%M:%S')"
    echo "----------------------------------------"
    echo ""

    sleep $INTERVAL
done
