#!/usr/bin/env python
"""
下载所有A股数据
包括元数据和K线数据（日、周、月）
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_settings
from src.services.data_pipeline import MarketDataService
from src.services.tushare_data_provider import TushareDataProvider
from src.models import Timeframe
from src.database import init_db, SessionLocal
from src.models import SymbolMetadata

def main():
    print("=" * 60)
    print("  下载所有A股数据")
    print("=" * 60)

    # 1. 初始化数据库
    print("\n1. 初始化数据库...")
    init_db()
    print("✓ 数据库初始化完成")

    # 2. 获取股票列表
    print("\n2. 获取股票列表...")
    provider = TushareDataProvider()
    all_tickers = provider.fetch_all_tickers()
    print(f"✓ 获取到 {len(all_tickers)} 只股票")

    # 检查已下载的股票
    session = SessionLocal()
    try:
        existing_stocks = session.query(SymbolMetadata).all()
        existing_tickers = set(stock.ticker for stock in existing_stocks)
        print(f"✓ 数据库中已有 {len(existing_tickers)} 只股票")

        # 找出需要下载的股票
        remaining_tickers = [t for t in all_tickers if t not in existing_tickers]

        if remaining_tickers:
            print(f"✓ 需要下载 {len(remaining_tickers)} 只新股票")
            tickers_to_download = remaining_tickers
        else:
            print(f"⚠️  所有股票已存在，将刷新所有数据")
            tickers_to_download = all_tickers

    finally:
        session.close()

    # 3. 下载 K 线和元数据
    print("\n3. 开始下载数据...")
    print(f"   股票数量: {len(tickers_to_download)} 只")
    print(f"   时间框架: 日线、周线、月线")
    print(f"   每只股票: 200 根 K 线")

    # 估算时间
    # 每只股票需要约 4 次API调用（元数据1次 + 3个时间框架各1次）
    total_calls = len(tickers_to_download) * 4
    estimated_minutes = total_calls / 180  # 180次/分钟

    print(f"\n   预计API调用: {total_calls} 次")
    print(f"   预计时间: {estimated_minutes:.1f} 分钟 ({estimated_minutes/60:.1f} 小时)")
    print(f"\n   开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    service = MarketDataService(provider=provider)

    # 批量下载，每100只打印一次进度
    batch_size = 100
    total = len(tickers_to_download)

    try:
        for i in range(0, total, batch_size):
            batch = tickers_to_download[i:i+batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size

            print(f"\n批次 {batch_num}/{total_batches}: 下载第 {i+1}-{min(i+batch_size, total)} 只股票...")

            try:
                service.refresh_universe(
                    tickers=batch,
                    timeframes=[Timeframe.DAY, Timeframe.WEEK, Timeframe.MONTH]
                )
                print(f"✓ 批次 {batch_num} 完成")

            except Exception as e:
                print(f"❌ 批次 {batch_num} 失败: {e}")
                print("继续下一批次...")
                continue

        print("\n✓ 所有批次下载完成")

    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断下载")
        print(f"已下载数据已保存到数据库")
        return 1

    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("\n" + "=" * 60)
    print("  ✅ 数据下载完成！")
    print("=" * 60)
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n统计信息:")

    # 统计下载结果
    session = SessionLocal()
    try:
        from src.models import Candle
        from sqlalchemy import func, distinct

        stock_count = session.query(SymbolMetadata).count()
        candle_count = session.query(Candle).count()
        day_candles = session.query(Candle).filter(Candle.timeframe == 'day').count()
        week_candles = session.query(Candle).filter(Candle.timeframe == 'week').count()
        month_candles = session.query(Candle).filter(Candle.timeframe == 'month').count()

        print(f"  股票数量: {stock_count}")
        print(f"  K线总数: {candle_count}")
        print(f"  - 日线: {day_candles}")
        print(f"  - 周线: {week_candles}")
        print(f"  - 月线: {month_candles}")

    finally:
        session.close()

    print("\n下一步:")
    print("1. 映射股票到90个核心行业: python scripts/map_stocks_to_core_industries.py")
    print("2. 启动应用: uvicorn src.main:app --reload")
    print("3. 访问前端: http://localhost:5173")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
