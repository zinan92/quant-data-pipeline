"""
手动触发K线数据更新
用于补充缺失的交易日数据
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.kline_updater import KlineUpdater
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def main():
    """手动更新所有K线数据"""
    updater = KlineUpdater()

    print("=" * 60)
    print("手动更新K线数据")
    print("=" * 60)

    # 1. 更新指数日线
    print("\n[1/5] 更新指数日线...")
    try:
        count = await updater.update_index_daily()
        print(f"✅ 指数日线更新完成: {count} 条")
    except Exception as e:
        print(f"❌ 指数日线更新失败: {e}")

    # 2. 更新概念日线
    print("\n[2/5] 更新概念日线...")
    try:
        count = await updater.update_concept_daily()
        print(f"✅ 概念日线更新完成: {count} 条")
    except Exception as e:
        print(f"❌ 概念日线更新失败: {e}")

    # 3. 更新指数30分钟线
    print("\n[3/5] 更新指数30分钟线...")
    try:
        count = await updater.update_index_30m()
        print(f"✅ 指数30分钟线更新完成: {count} 条")
    except Exception as e:
        print(f"❌ 指数30分钟线更新失败: {e}")

    # 4. 更新概念30分钟线
    print("\n[4/5] 更新概念30分钟线...")
    try:
        count = await updater.update_concept_30m()
        print(f"✅ 概念30分钟线更新完成: {count} 条")
    except Exception as e:
        print(f"❌ 概念30分钟线更新失败: {e}")

    # 5. 更新自选股K线
    print("\n[5/5] 更新自选股K线...")
    try:
        daily_count = await updater.update_stock_daily()
        mins30_count = await updater.update_stock_30m()
        print(f"✅ 自选股更新完成: 日线 {daily_count} 条, 30分钟 {mins30_count} 条")
    except Exception as e:
        print(f"❌ 自选股更新失败: {e}")

    print("\n" + "=" * 60)
    print("更新完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
