"""
为数据库中的23个watchlist股票生成综合信息CSV
包含: ticker, name, 板块
"""

import pandas as pd
from pathlib import Path

import sys
sys.path.insert(0, '/Users/park/a-share-data')

from src.database import session_scope
from src.models import SymbolMetadata


def main():
    print("=" * 70)
    print("为Watchlist生成综合信息CSV")
    print("=" * 70)

    # 1. 从数据库获取watchlist的23个股票
    print("\n📊 步骤1: 从数据库读取watchlist...")

    with session_scope() as session:
        stocks = session.query(SymbolMetadata).all()
        print(f"  ✓ 共 {len(stocks)} 只股票")

        # 2. 读取行业板块CSV，构建ticker到板块名称和代码的映射
        print("\n📊 步骤2: 读取行业板块数据...")
        industry_csv = Path("data/industry_board_constituents.csv")
        industry_df = pd.read_csv(industry_csv)

        # 构建映射：ticker -> (板块名称, 板块代码)
        ticker_to_board_info = {}
        for _, row in industry_df.iterrows():
            board_name = row['板块名称']    # 第1列
            board_code = row['板块代码']    # 第2列
            constituents = str(row['成分股列表']).split(',')

            for ticker in constituents:
                ticker = ticker.strip()
                if ticker and ticker != 'ERROR: Failed after retries':
                    ticker_to_board_info[ticker] = {
                        'board_name': board_name,
                        'board_code': board_code
                    }

        print(f"  ✓ 已加载行业板块映射")

        # 3. 构建股票数据
        print("\n📊 步骤3: 构建股票数据...")
        stock_data = []

        for idx, stock in enumerate(stocks, 1):
            # 获取板块信息
            board_info = ticker_to_board_info.get(stock.ticker, {})

            # 构建数据行
            stock_data.append({
                'ticker': stock.ticker,
                'name': stock.name,
                '板块': board_info.get('board_name', ''),  # 板块名称
            })

        print(f"  ✓ 已处理 {len(stock_data)} 只股票")

    # 4. 保存CSV
    print("\n📊 步骤4: 保存CSV文件...")
    output_df = pd.DataFrame(stock_data)

    output_file = Path("data/watchlist_info.csv")
    output_df.to_csv(output_file, index=False, encoding='utf-8')

    print(f"  ✓ 已保存到: {output_file}")
    print(f"  ✓ 总记录数: {len(output_df)}")

    # 5. 统计
    print("\n" + "=" * 70)
    print("✅ 完成")
    print("=" * 70)

    print(f"\n📈 数据统计:")
    print(f"  • 总股票数: {len(output_df)}")
    print(f"  • 有板块信息: {(output_df['板块'] != '').sum()} ({(output_df['板块'] != '').sum()/len(output_df)*100:.1f}%)")

    print(f"\n📋 CSV预览:")
    print(output_df.to_string(index=False))


if __name__ == "__main__":
    main()
