#!/usr/bin/env python3
"""强制更新监控数据 - 诊断版本"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import akshare as ak
import json
from datetime import datetime

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "monitor"
OUTPUT_FILE = OUTPUT_DIR / 'latest.json'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("强制更新监控数据")
print("=" * 60)

try:
    print("\n1. 获取概念板块列表...")
    df_names = ak.stock_board_concept_name_ths()
    print(f"   ✅ 获取到 {len(df_names)} 个概念板块")

    print("\n2. 获取前20个概念板块详情...")
    top_concepts = []

    for idx, row in df_names.head(20).iterrows():
        concept_name = row['name']
        concept_code = row['code']

        try:
            print(f"   处理: {concept_name} ({concept_code})")
            df_info = ak.stock_board_concept_info_ths(symbol=concept_name)

            if not df_info.empty:
                info_row = df_info.iloc[0]
                top_concepts.append({
                    'name': concept_name,
                    'code': concept_code,
                    'changePct': float(info_row.get('涨跌幅', 0)),
                    'changeValue': float(info_row.get('涨跌', 0)),
                    'moneyInflow': float(info_row.get('资金流入', 0)),
                    'volumeRatio': float(info_row.get('量比', 0)),
                    'upCount': int(info_row.get('上涨家数', 0)),
                    'downCount': int(info_row.get('下跌家数', 0)),
                    'limitUp': 0,  # 简化版本，不查询涨停数
                    'totalStocks': int(info_row.get('上涨家数', 0)) + int(info_row.get('下跌家数', 0)),
                    'turnover': float(info_row.get('换手率', 0)),
                    'volume': float(info_row.get('总成交量', 0)),
                    'day5Change': 0,  # 简化版本
                    'day10Change': 0,
                    'day20Change': 0
                })

        except Exception as e:
            print(f"   ⚠️  获取 {concept_name} 失败: {e}")
            continue

    print(f"\n3. 保存数据到 {OUTPUT_FILE}...")
    output_data = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'topConcepts': {
            'data': top_concepts
        },
        'watchConcepts': {
            'data': []  # 简化版本
        }
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"   ✅ 成功保存 {len(top_concepts)} 个概念板块")
    print(f"   更新时间: {output_data['timestamp']}")

    print("\n" + "=" * 60)
    print("✅ 更新完成")
    print("=" * 60)

except Exception as e:
    print(f"\n❌ 更新失败: {e}")
    import traceback
    traceback.print_exc()
