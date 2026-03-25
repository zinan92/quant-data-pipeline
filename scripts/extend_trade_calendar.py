#!/usr/bin/env python3
"""
扩展交易日历到2021-2026年

手动执行脚本，用于回填交易日历数据
支持幂等操作（可重复运行）

用法:
    python scripts/extend_trade_calendar.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime

from src.database import SessionLocal
from src.repositories.kline_repository import KlineRepository
from src.services.calendar_updater import CalendarUpdater
from src.utils.logging import get_logger

logger = get_logger(__name__)


def main():
    """扩展交易日历到2021-2026年"""
    logger.info("开始扩展交易日历...")
    logger.info("目标范围: 2021-01-01 到 2026-12-31")

    session = SessionLocal()
    try:
        kline_repo = KlineRepository(session)
        updater = CalendarUpdater(kline_repo)

        # 调用update_trade_calendar，它现在自动从2021年到明年
        count = updater.update_trade_calendar()

        logger.info(f"✓ 交易日历扩展完成，处理了 {count} 条记录")
        logger.info("验证结果...")

        # 验证日期范围
        from src.models import TradeCalendar

        min_date = (
            session.query(TradeCalendar.date)
            .order_by(TradeCalendar.date)
            .first()
        )
        max_date = (
            session.query(TradeCalendar.date)
            .order_by(TradeCalendar.date.desc())
            .first()
        )

        trading_days = (
            session.query(TradeCalendar)
            .filter(TradeCalendar.is_trading_day == 1)
            .count()
        )

        logger.info(f"  日期范围: {min_date[0]} 至 {max_date[0]}")
        logger.info(f"  交易日数量: {trading_days}")

        # 检查是否符合预期
        if min_date[0] <= "2021-01-04" and max_date[0] >= "2026-12-31":
            logger.info("✓ 日期范围检查通过")
        else:
            logger.warning(
                f"⚠ 日期范围未达到预期 (最小: {min_date[0]}, 最大: {max_date[0]})"
            )

        if 1300 <= trading_days <= 1700:
            logger.info("✓ 交易日数量检查通过 (1300-1700范围内)")
        else:
            logger.warning(f"⚠ 交易日数量 {trading_days} 不在预期范围内 (1300-1700)")

    except Exception as e:
        logger.exception(f"扩展交易日历失败: {e}")
        sys.exit(1)
    finally:
        session.close()

    logger.info("完成！")


if __name__ == "__main__":
    main()
