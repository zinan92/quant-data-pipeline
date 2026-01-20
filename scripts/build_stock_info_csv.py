"""
构建以ticker为key的股票综合信息CSV

包含字段:
- ticker: 股票代码
- name: 股票名称
- industry_board: 所属行业板块
- market_cap: 市值
- industry_lv1/2/3: 多级行业分类
- concepts: 概念板块列表
"""

import pandas as pd
from pathlib import Path
from collections import defaultdict

from src.database import session_scope
from src.models import SymbolMetadata


def main():
    print("=" * 70)
    print("构建股票综合信息CSV")
    print("=" * 70)

    # 1. 读取行业板块CSV，构建ticker到板块的映射
    print("\n📊 步骤1: 读取行业板块数据...")
    industry_csv = Path("data/industry_board_constituents.csv")
    industry_df = pd.read_csv(industry_csv)

    ticker_to_industry = {}
    for _, row in industry_df.iterrows():
        board_name = row['板块名称']
        constituents = str(row['成分股列表']).split(',')

        for ticker in constituents:
            ticker = ticker.strip()
            if ticker and ticker != 'ERROR: Failed after retries':
                ticker_to_industry[ticker] = board_name

    print(f"  ✓ 已加载 {len(ticker_to_industry)} 个ticker的行业板块信息")

    # 2. 从数据库获取股票元数据
    print("\n📊 步骤2: 从数据库获取股票元数据...")
    stocks_data = []

    with session_scope() as session:
        all_stocks = session.query(SymbolMetadata).all()
        print(f"  ✓ 数据库中有 {len(all_stocks)} 只股票")

        for stock in all_stocks:
            stocks_data.append({
                'ticker': stock.ticker,
                'name': stock.name,
                'market_cap': stock.market_cap,
                'industry_lv1': stock.industry_lv1,
                'industry_lv2': stock.industry_lv2,
                'industry_lv3': stock.industry_lv3,
                'concepts': stock.concepts,
            })

    # 3. 合并所有ticker（数据库 + CSV中的ticker）
    print("\n📊 步骤3: 合并所有ticker...")
    all_tickers = set(ticker_to_industry.keys())
    db_tickers = set(s['ticker'] for s in stocks_data)

    print(f"  • 行业板块CSV中的ticker: {len(all_tickers)}")
    print(f"  • 数据库中的ticker: {len(db_tickers)}")
    print(f"  • 仅在CSV中: {len(all_tickers - db_tickers)}")
    print(f"  • 仅在DB中: {len(db_tickers - all_tickers)}")

    # 4. 构建综合数据
    print("\n📊 步骤4: 构建综合数据表...")
    db_dict = {s['ticker']: s for s in stocks_data}

    comprehensive_data = []
    for ticker in all_tickers:
        # 基础信息（如果在数据库中）
        if ticker in db_dict:
            stock_info = db_dict[ticker]
            row = {
                'ticker': ticker,
                'name': stock_info['name'],
                'industry_board': ticker_to_industry.get(ticker, ''),
                'market_cap': stock_info['market_cap'],
                'industry_lv1': stock_info['industry_lv1'],
                'industry_lv2': stock_info['industry_lv2'],
                'industry_lv3': stock_info['industry_lv3'],
                'concepts': ','.join(stock_info['concepts']) if stock_info['concepts'] else '',
            }
        else:
            # 仅有行业板块信息
            row = {
                'ticker': ticker,
                'name': '',
                'industry_board': ticker_to_industry.get(ticker, ''),
                'market_cap': None,
                'industry_lv1': '',
                'industry_lv2': '',
                'industry_lv3': '',
                'concepts': '',
            }

        comprehensive_data.append(row)

    # 5. 保存CSV
    print("\n📊 步骤5: 保存CSV文件...")
    output_df = pd.DataFrame(comprehensive_data)
    output_df = output_df.sort_values('ticker')

    output_file = Path("data/stock_comprehensive_info.csv")
    output_df.to_csv(output_file, index=False, encoding='utf-8')

    print(f"  ✓ 已保存到: {output_file}")
    print(f"  ✓ 总记录数: {len(output_df)}")

    # 6. 统计
    print("\n" + "=" * 70)
    print("✅ 完成")
    print("=" * 70)

    print(f"\n📈 数据统计:")
    print(f"  • 总ticker数: {len(output_df)}")
    print(f"  • 有名称的: {output_df['name'].notna().sum()} ({output_df['name'].notna().sum()/len(output_df)*100:.1f}%)")
    print(f"  • 有行业板块的: {output_df['industry_board'].notna().sum()} ({output_df['industry_board'].notna().sum()/len(output_df)*100:.1f}%)")
    print(f"  • 有市值的: {output_df['market_cap'].notna().sum()} ({output_df['market_cap'].notna().sum()/len(output_df)*100:.1f}%)")

    print(f"\n📝 CSV字段:")
    print(f"  1. ticker - 股票代码")
    print(f"  2. name - 股票名称")
    print(f"  3. industry_board - 所属行业板块")
    print(f"  4. market_cap - 市值")
    print(f"  5. industry_lv1/2/3 - 多级行业分类")
    print(f"  6. concepts - 概念板块列表")

    print(f"\n📋 示例数据 (前5条):")
    print(output_df.head()[['ticker', 'name', 'industry_board', 'market_cap']].to_string(index=False))


if __name__ == "__main__":
    main()
