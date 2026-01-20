#!/usr/bin/env python
"""
获取同花顺行业板块列表及成分股数量
保存到CSV文件
"""

import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.tushare_client import TushareClient
from src.config import get_settings

def main():
    print("=" * 60)
    print("  获取同花顺行业板块数据")
    print("=" * 60)

    settings = get_settings()
    client = TushareClient(
        token=settings.tushare_token,
        points=settings.tushare_points
    )

    # 获取行业板块列表
    print("\n1. 获取行业板块列表...")
    industry_df = client.fetch_ths_index(exchange='A', type='I')
    print(f"✓ 获取到 {len(industry_df)} 个行业板块")

    # 准备结果数据
    results = []
    total_stocks = 0

    print("\n2. 获取每个板块的成分股数量...")
    for idx, row in industry_df.iterrows():
        board_code = row['ts_code']
        board_name = row['name']

        try:
            # 获取成分股
            members_df = client.fetch_ths_member(ts_code=board_code)

            # 统计成分股数量
            if not members_df.empty:
                code_field = 'con_code' if 'con_code' in members_df.columns else 'code'
                stock_count = len(members_df[code_field].dropna())
            else:
                stock_count = 0

            results.append({
                '板块代码': board_code,
                '板块名称': board_name,
                '成分股数量': stock_count
            })

            total_stocks += stock_count

            # 打印前20个
            if idx < 20:
                print(f"  {board_name}: {stock_count}只股票")
            elif idx == 20:
                print("  ...")

        except Exception as e:
            print(f"  ❌ 获取 {board_name} 失败: {e}")
            results.append({
                '板块代码': board_code,
                '板块名称': board_name,
                '成分股数量': 0
            })

    # 创建DataFrame并排序
    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values('成分股数量', ascending=False)

    # 保存到CSV
    output_file = project_root / 'data' / 'ths_industry_boards.csv'
    result_df.to_csv(output_file, index=False, encoding='utf-8-sig')

    print("\n" + "=" * 60)
    print("  ✅ 完成！")
    print("=" * 60)
    print(f"\n总板块数: {len(result_df)}")
    print(f"总成分股: {total_stocks}")
    print(f"\n前10个板块:")
    print(result_df.head(10).to_string(index=False))
    print(f"\n已保存到: {output_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
