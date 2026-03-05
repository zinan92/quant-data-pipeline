#!/usr/bin/env python3
"""
测试脚本：生成模拟的surge信号
用于演示动量信号功能
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import datetime

# 读取现有的signals文件
SIGNALS_FILE = Path(__file__).resolve().parent.parent / "data" / "monitor" / "momentum_signals.json"

with open(SIGNALS_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 添加模拟的surge信号
simulated_surge_signals = [
    {
        "concept_name": "人工智能",
        "concept_code": "885463",
        "signal_type": "surge",
        "total_stocks": 156,
        "prev_up_count": 45,
        "current_up_count": 52,
        "delta_up_count": 7,
        "threshold": 5,
        "board_type": "large",
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "details": "7只新增上涨 (阈值: 5只)"
    },
    {
        "concept_name": "芯片概念",
        "concept_code": "885657",
        "signal_type": "surge",
        "total_stocks": 203,
        "prev_up_count": 78,
        "current_up_count": 84,
        "delta_up_count": 6,
        "threshold": 5,
        "board_type": "large",
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "details": "6只新增上涨 (阈值: 5只)"
    },
    {
        "concept_name": "CPO概念",
        "concept_code": "886094",
        "signal_type": "surge",
        "total_stocks": 42,
        "prev_up_count": 15,
        "current_up_count": 19,
        "delta_up_count": 4,
        "threshold": 3,
        "board_type": "small",
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "details": "4只新增上涨 (阈值: 3只)"
    }
]

# 合并信号
all_signals = simulated_surge_signals + data['signals'][:8]  # 保留前8个K线信号

# 更新数据
updated_data = {
    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'total_signals': len(all_signals),
    'surge_signals_count': len(simulated_surge_signals),
    'kline_signals_count': 8,
    'signals': all_signals
}

# 保存
with open(SIGNALS_FILE, 'w', encoding='utf-8') as f:
    json.dump(updated_data, f, ensure_ascii=False, indent=2)

print(f"✅ 已生成测试信号:")
print(f"   - 总信号数: {updated_data['total_signals']}")
print(f"   - 上涨激增: {updated_data['surge_signals_count']}")
print(f"   - K线形态: {updated_data['kline_signals_count']}")
print(f"   - 更新时间: {updated_data['timestamp']}")
print(f"\n📊 上涨激增信号:")
for signal in simulated_surge_signals:
    print(f"   • {signal['concept_name']}: {signal['details']}")
