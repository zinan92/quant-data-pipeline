#!/usr/bin/env python
"""更新所有股票的K线数据到最新交易日"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import SessionLocal
from src.models import SymbolMetadata, Timeframe
from src.services.data_pipeline import MarketDataService
from src.utils.logging import LOGGER

def main():
    print("=" * 60)
    print("  更新所有股票K线数据")
    print("=" * 60)

    session = SessionLocal()

    try:
        # 获取所有股票
        symbols = session.query(SymbolMetadata).all()
        tickers = [s.ticker for s in symbols]

        print(f"\n找到 {len(tickers)} 个股票")
        print("开始更新日线数据...")

        # 使用data_pipeline服务更新
        service = MarketDataService()

        # 分批更新，避免一次性更新太多
        BATCH_SIZE = 100
        total_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE

        for i in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1

            print(f"\n[批次 {batch_num}/{total_batches}] 更新 {len(batch)} 个股票...")

            try:
                service.refresh_universe(
                    tickers=batch,
                    timeframes=[Timeframe.DAY]
                )
                print(f"  ✅ 批次 {batch_num} 完成")
            except Exception as e:
                print(f"  ❌ 批次 {batch_num} 失败: {e}")
                continue

        print("\n" + "=" * 60)
        print("  ✅ 更新完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()

    return 0

if __name__ == "__main__":
    sys.exit(main())
