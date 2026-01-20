#!/usr/bin/env python
"""
获取东方财富概念板块列表
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
    print("  获取东方财富概念板块数据")
    print("=" * 60)

    settings = get_settings()
    client = TushareClient(
        token=settings.tushare_token,
        points=settings.tushare_points
    )

    # 获取最新交易日
    print("\n1. 获取最新交易日...")
    latest_date = client.get_latest_trade_date()
    print(f"   最新交易日: {latest_date}")

    # 获取东方财富概念板块列表
    print("\n2. 获取东方财富概念板块列表...")
    df = client.fetch_dc_index(trade_date=latest_date)

    if df.empty:
        print("❌ 未获取到数据")
        return 1

    print(f"   ✓ 获取到 {len(df)} 个概念板块")

    # 选择需要的字段并重命名为中文
    result_df = df[['ts_code', 'name', 'leading', 'leading_code',
                     'pct_change', 'leading_pct', 'total_mv',
                     'turnover_rate', 'up_num', 'down_num']].copy()

    result_df.rename(columns={
        'ts_code': '板块代码',
        'name': '板块名称',
        'leading': '领涨股名称',
        'leading_code': '领涨股代码',
        'pct_change': '板块涨跌幅',
        'leading_pct': '领涨股涨跌幅',
        'total_mv': '总市值(万元)',
        'turnover_rate': '换手率',
        'up_num': '上涨家数',
        'down_num': '下跌家数'
    }, inplace=True)

    # 按涨跌幅排序
    result_df = result_df.sort_values('板块涨跌幅', ascending=False)

    # 保存到CSV
    output_file = project_root / 'data' / 'dc_concept_boards.csv'
    result_df.to_csv(output_file, index=False, encoding='utf-8-sig')

    print("\n" + "=" * 60)
    print("  ✅ 完成！")
    print("=" * 60)
    print(f"\n总板块数: {len(result_df)}")
    print(f"数据日期: {latest_date}")

    print(f"\n涨幅前10的板块:")
    print(result_df[['板块名称', '板块涨跌幅', '上涨家数', '下跌家数']].head(10).to_string(index=False))

    print(f"\n跌幅前10的板块:")
    print(result_df[['板块名称', '板块涨跌幅', '上涨家数', '下跌家数']].tail(10).to_string(index=False))

    print(f"\n已保存到: {output_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
