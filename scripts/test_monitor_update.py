#!/usr/bin/env python3
"""测试监控脚本数据获取"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import akshare as ak
from datetime import datetime

print("=" * 60)
print("测试AKShare API连接")
print("=" * 60)

try:
    print("\n1. 测试获取概念板块数据...")
    df = ak.stock_board_concept_name_ths()
    print(f"   ✅ 成功获取 {len(df)} 个概念板块")
    print(f"   示例数据:")
    print(df.head(3))

    print("\n2. 测试获取概念成分股...")
    first_concept = df.iloc[0]['name']
    print(f"   测试概念: {first_concept}")
    df_cons = ak.stock_board_concept_cons_ths(symbol=first_concept)
    print(f"   ✅ 成功获取 {len(df_cons)} 只成分股")

    print("\n3. 检查数据文件状态...")
    monitor_dir = Path(__file__).resolve().parent.parent / "data" / "monitor"
    output_file = monitor_dir / "latest.json"
    signals_file = monitor_dir / "momentum_signals.json"

    if output_file.exists():
        import json
        with open(output_file, 'r') as f:
            data = json.load(f)
        print(f"   latest.json 存在，更新时间: {data.get('timestamp', '未知')}")
    else:
        print(f"   ❌ latest.json 不存在")

    if signals_file.exists():
        import json
        with open(signals_file, 'r') as f:
            data = json.load(f)
        print(f"   momentum_signals.json 存在，更新时间: {data.get('timestamp', '未知')}")
    else:
        print(f"   ❌ momentum_signals.json 不存在")

    print("\n" + "=" * 60)
    print("✅ 测试完成 - API连接正常")
    print("=" * 60)

except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
