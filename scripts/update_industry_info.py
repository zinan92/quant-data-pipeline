#!/usr/bin/env python
"""
更新股票的行业信息
从Tushare获取industry字段并更新到数据库
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func
from src.database import SessionLocal
from src.models import SymbolMetadata
from src.services.tushare_data_provider import TushareDataProvider

def main():
    print("=" * 60)
    print("  更新股票行业信息")
    print("=" * 60)

    session = SessionLocal()
    provider = TushareDataProvider()

    try:
        # 获取所有股票
        all_stocks = session.query(SymbolMetadata).all()
        print(f"\n找到 {len(all_stocks)} 只股票")

        # 获取完整的股票列表（包含行业信息）
        print("\n获取Tushare股票列表...")
        stock_list_df = provider.client.fetch_stock_list()
        print(f"✓ 获取到 {len(stock_list_df)} 只股票信息")

        # 更新每只股票的行业信息
        updated = 0
        for stock in all_stocks:
            ts_code = provider.client.normalize_ts_code(stock.ticker)
            stock_info = stock_list_df[stock_list_df['ts_code'] == ts_code]

            if not stock_info.empty and 'industry' in stock_info.columns:
                industry = stock_info['industry'].iloc[0]
                if industry and str(industry) != 'nan':
                    stock.industry_lv1 = str(industry)
                    updated += 1
                    if updated <= 10:  # 只打印前10个
                        print(f"  ✓ {stock.ticker} {stock.name} → {industry}")

        session.commit()
        print(f"\n✅ 成功更新 {updated} 只股票的行业信息")

        # 显示行业统计
        print("\n行业分布（前10名）：")
        industries = session.query(
            SymbolMetadata.industry_lv1,
            func.count(SymbolMetadata.ticker).label('count')
        ).filter(
            SymbolMetadata.industry_lv1.isnot(None)
        ).group_by(
            SymbolMetadata.industry_lv1
        ).order_by(
            func.count(SymbolMetadata.ticker).desc()
        ).limit(10).all()

        for industry, count in industries:
            print(f"  {industry}: {count}只")

    except Exception as e:
        session.rollback()
        print(f"\n❌ 更新失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        session.close()

    print("\n" + "=" * 60)
    print("  ✅ 更新完成！")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
