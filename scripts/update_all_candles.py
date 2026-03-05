#!/usr/bin/env python
"""更新所有股票的K线数据到最新交易日"""

import sys
from pathlib import Path
import asyncio

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import SessionLocal
from src.services.kline_updater import KlineUpdater

def main():
    print("=" * 60)
    print("  更新全市场股票日线数据")
    print("=" * 60)

    session = SessionLocal()

    try:
        updater = KlineUpdater.create_with_session(session)
        print("\n开始执行全市场日线更新...")
        updated = asyncio.run(updater.update_all_stock_daily())
        print(f"\n  ✅ 完成，写入/更新 {updated} 条K线")

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
