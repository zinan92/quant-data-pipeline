#!/usr/bin/env python
"""为现有自选股补充买入价格数据"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import SessionLocal
from src.models import Watchlist, Candle, Timeframe
from sqlalchemy import desc

def backfill_purchase_data():
    print("=" * 60)
    print("  为现有自选股补充买入价格数据")
    print("=" * 60)

    session = SessionLocal()

    try:
        # 获取所有没有买入价格的自选股
        watchlist_items = session.query(Watchlist).filter(
            Watchlist.purchase_price.is_(None)
        ).all()

        if not watchlist_items:
            print("\n所有自选股都已有买入价格数据")
            return

        print(f"\n找到 {len(watchlist_items)} 个需要补充数据的自选股")

        updated_count = 0

        for item in watchlist_items:
            # 获取该股票最新的收盘价
            latest_candle = session.query(Candle).filter(
                Candle.ticker == item.ticker,
                Candle.timeframe == Timeframe.DAY
            ).order_by(desc(Candle.timestamp)).first()

            if latest_candle and latest_candle.close:
                purchase_price = float(latest_candle.close)
                shares = 10000.0 / purchase_price if purchase_price > 0 else None

                # 更新数据
                item.purchase_price = purchase_price
                item.purchase_date = item.added_at  # 使用添加日期作为买入日期
                item.shares = shares

                print(f"  ✓ {item.ticker}: 买入价=¥{purchase_price:.2f}, 股数={shares:.2f}")
                updated_count += 1
            else:
                print(f"  ⚠️  {item.ticker}: 未找到K线数据")

        session.commit()

        print("\n" + "=" * 60)
        print(f"  ✅ 完成！更新了 {updated_count} 个自选股")
        print("=" * 60)

    except Exception as e:
        session.rollback()
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()

    return 0

if __name__ == "__main__":
    sys.exit(backfill_purchase_data())
