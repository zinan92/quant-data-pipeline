#!/bin/bash
# 同花顺概念板块K线数据每日更新脚本
# 建议在交易日收盘后运行 (15:30 之后)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/concept_kline_update_$(date +%Y%m%d).log"

# 创建日志目录
mkdir -p "$LOG_DIR"

echo "========================================" >> "$LOG_FILE"
echo "开始更新: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 进入项目目录
cd "$PROJECT_DIR"

# 运行更新脚本
python3 scripts/fetch_ths_concept_kline.py -u >> "$LOG_FILE" 2>&1

echo "" >> "$LOG_FILE"
echo "更新完成: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# 清理30天前的日志
find "$LOG_DIR" -name "concept_kline_update_*.log" -mtime +30 -delete 2>/dev/null || true
