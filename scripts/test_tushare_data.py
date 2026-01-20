#!/usr/bin/env python
"""测试Tushare Pro是否有指定日期的数据"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.tushare_client import TushareClient
from src.config import get_settings

def test_date_data(trade_date: str):
    """测试指定日期是否有数据

    Args:
        trade_date: 交易日期 YYYYMMDD
    """
    print(f"\n{'='*60}")
    print(f"  测试日期: {trade_date}")
    print(f"{'='*60}")

    settings = get_settings()
    client = TushareClient(
        token=settings.tushare_token,
        points=settings.tushare_points
    )

    # 1. 测试日线数据（个股）
    print("\n1. 测试个股日线数据 (以600519贵州茅台为例)...")
    try:
        df_daily = client.fetch_daily(
            ts_code="600519.SH",
            start_date=trade_date,
            end_date=trade_date
        )
        if not df_daily.empty:
            print(f"   ✅ 找到数据: {len(df_daily)} 条记录")
            print(f"   示例数据:")
            print(df_daily[['ts_code', 'trade_date', 'close', 'pct_chg']].to_string())
        else:
            print(f"   ❌ 无数据")
    except Exception as e:
        print(f"   ❌ 错误: {e}")

    # 2. 测试行业资金流向数据
    print("\n2. 测试同花顺行业资金流向数据...")
    try:
        df_industry = client.fetch_ths_industry_moneyflow(trade_date=trade_date)
        if not df_industry.empty:
            print(f"   ✅ 找到数据: {len(df_industry)} 个行业")
            print(f"   示例数据 (前5个):")
            print(df_industry.head()[['industry', 'close', 'pct_change']].to_string())
        else:
            print(f"   ❌ 无数据")
    except Exception as e:
        print(f"   ❌ 错误: {e}")

    # 3. 测试多个股票
    print("\n3. 测试多个股票的日线数据...")
    test_stocks = ["600519.SH", "000001.SZ", "688256.SH"]
    for stock in test_stocks:
        try:
            df = client.fetch_daily(
                ts_code=stock,
                start_date=trade_date,
                end_date=trade_date
            )
            if not df.empty:
                close = df.iloc[0]['close']
                pct_chg = df.iloc[0]['pct_chg']
                print(f"   ✅ {stock}: 收盘价={close}, 涨跌幅={pct_chg}%")
            else:
                print(f"   ❌ {stock}: 无数据")
        except Exception as e:
            print(f"   ❌ {stock}: 错误 - {e}")

if __name__ == "__main__":
    # 测试11-15, 11-17, 11-18
    test_dates = ["20251115", "20251117", "20251118"]

    for date in test_dates:
        test_date_data(date)

    print(f"\n{'='*60}")
    print("  测试完成")
    print(f"{'='*60}\n")
