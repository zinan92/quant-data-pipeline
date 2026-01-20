#!/usr/bin/env python
"""
K线数据检查和重置脚本

用途:
1. 检查数据库中K线数据的新鲜度
2. 清理过时数据，准备增量更新
3. 强制重置所有数据，进行全量下载

使用方法:
    # 检查数据新鲜度
    python scripts/check_and_reset_candles.py --check

    # 清理超过30天的过时数据
    python scripts/check_and_reset_candles.py --clean-stale --days 30

    # 重置所有K线数据（慎用！）
    python scripts/check_and_reset_candles.py --reset-all --confirm

    # 重置指定ticker的数据
    python scripts/check_and_reset_candles.py --reset-ticker 000001
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func, delete
from src.database import SessionLocal
from src.models import Candle, Timeframe


def check_data_freshness():
    """检查K线数据新鲜度"""
    session = SessionLocal()

    try:
        print("=" * 60)
        print("K线数据新鲜度检查")
        print("=" * 60)

        # 统计总数
        total_count = session.query(func.count(Candle.id)).scalar()
        print(f"\n📊 总K线数量: {total_count:,} 条")

        if total_count == 0:
            print("\n✅ 数据库为空，首次refresh将进行全量下载")
            return

        # 按timeframe统计
        print("\n按时间周期统计:")
        print("-" * 60)
        print(f"{'Timeframe':<15} {'数量':<15} {'最新日期':<20} {'过时天数':<10}")
        print("-" * 60)

        now = datetime.now(timezone.utc)
        stale_found = False

        for tf in [Timeframe.DAY, Timeframe.WEEK, Timeframe.MONTH]:
            count = session.query(func.count(Candle.id)).filter(
                Candle.timeframe == tf
            ).scalar()

            latest = session.query(func.max(Candle.timestamp)).filter(
                Candle.timeframe == tf
            ).scalar()

            if latest:
                # 处理 naive datetime
                if latest.tzinfo is None:
                    latest = latest.replace(tzinfo=timezone.utc)

                days_old = (now - latest).days
                status = "🟢" if days_old <= 7 else "🟡" if days_old <= 30 else "🔴"

                if days_old > 30:
                    stale_found = True

                print(f"{status} {tf.value:<12} {count:>10,} 条    {latest.date()}    {days_old:>5} 天")
            else:
                print(f"  {tf.value:<12} {count:>10,} 条    N/A")

        print("-" * 60)

        # 按ticker抽样检查
        print("\n🔍 随机抽样检查 (10个ticker):")
        print("-" * 60)
        print(f"{'Ticker':<10} {'Timeframe':<12} {'最新日期':<15} {'过时天数':<10}")
        print("-" * 60)

        sample_tickers = session.query(Candle.ticker).distinct().limit(10).all()

        for (ticker,) in sample_tickers:
            latest_day = session.query(func.max(Candle.timestamp)).filter(
                Candle.ticker == ticker,
                Candle.timeframe == Timeframe.DAY
            ).scalar()

            if latest_day:
                if latest_day.tzinfo is None:
                    latest_day = latest_day.replace(tzinfo=timezone.utc)
                days_old = (now - latest_day).days
                status = "🟢" if days_old <= 7 else "🟡" if days_old <= 30 else "🔴"
                print(f"{status} {ticker:<8} DAY         {latest_day.date()}    {days_old:>5} 天")

        print("-" * 60)

        # 建议
        print("\n💡 建议:")
        if stale_found:
            print("⚠️  发现过时数据（超过30天）")
            print("   建议运行: python scripts/check_and_reset_candles.py --clean-stale --days 30")
        else:
            print("✅ 数据较新，可以直接使用增量更新")

    finally:
        session.close()


def clean_stale_data(days: int = 30):
    """清理超过指定天数的过时数据"""
    session = SessionLocal()

    try:
        print("=" * 60)
        print(f"清理超过 {days} 天的过时数据")
        print("=" * 60)

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # 查找过时数据
        stale_count = session.query(func.count(Candle.id)).filter(
            Candle.timestamp < cutoff_date
        ).scalar()

        if stale_count == 0:
            print(f"\n✅ 没有超过 {days} 天的过时数据")
            return

        print(f"\n🔍 发现 {stale_count:,} 条过时数据")
        print(f"   截止日期: {cutoff_date.date()}")

        confirm = input("\n⚠️  确认删除? (yes/no): ")

        if confirm.lower() != 'yes':
            print("❌ 已取消")
            return

        # 删除过时数据
        deleted = session.execute(
            delete(Candle).where(Candle.timestamp < cutoff_date)
        ).rowcount

        session.commit()

        print(f"\n✅ 已删除 {deleted:,} 条过时数据")
        print("   下次refresh将自动填补缺失数据")

    finally:
        session.close()


def reset_ticker_data(ticker: str):
    """重置指定ticker的K线数据"""
    session = SessionLocal()

    try:
        print("=" * 60)
        print(f"重置 ticker={ticker} 的K线数据")
        print("=" * 60)

        # 统计该ticker的数据
        count = session.query(func.count(Candle.id)).filter(
            Candle.ticker == ticker
        ).scalar()

        if count == 0:
            print(f"\n✅ ticker={ticker} 无数据")
            return

        print(f"\n🔍 发现 {count} 条K线数据")

        confirm = input(f"\n⚠️  确认删除 {ticker} 的所有K线数据? (yes/no): ")

        if confirm.lower() != 'yes':
            print("❌ 已取消")
            return

        # 删除数据
        deleted = session.execute(
            delete(Candle).where(Candle.ticker == ticker)
        ).rowcount

        session.commit()

        print(f"\n✅ 已删除 {deleted} 条K线数据")
        print(f"   下次refresh {ticker} 将进行全量下载")

    finally:
        session.close()


def reset_all_data(confirmed: bool = False):
    """重置所有K线数据（危险操作！）"""
    session = SessionLocal()

    try:
        print("=" * 60)
        print("⚠️  重置所有K线数据 (危险操作！)")
        print("=" * 60)

        total_count = session.query(func.count(Candle.id)).scalar()

        if total_count == 0:
            print("\n✅ 数据库已为空")
            return

        print(f"\n🔍 当前有 {total_count:,} 条K线数据")

        if not confirmed:
            print("\n⚠️  此操作将删除所有K线数据！")
            confirm = input("   请输入 'DELETE ALL' 确认: ")

            if confirm != 'DELETE ALL':
                print("❌ 已取消")
                return

        # 删除所有数据
        deleted = session.execute(delete(Candle)).rowcount
        session.commit()

        print(f"\n✅ 已删除 {deleted:,} 条K线数据")
        print("   数据库已清空，下次refresh将进行全量下载")

    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="K线数据检查和重置工具")
    parser.add_argument("--check", action="store_true", help="检查数据新鲜度")
    parser.add_argument("--clean-stale", action="store_true", help="清理过时数据")
    parser.add_argument("--days", type=int, default=30, help="定义过时天数（默认30天）")
    parser.add_argument("--reset-ticker", type=str, help="重置指定ticker的数据")
    parser.add_argument("--reset-all", action="store_true", help="重置所有数据（危险！）")
    parser.add_argument("--confirm", action="store_true", help="跳过确认提示")

    args = parser.parse_args()

    if args.check:
        check_data_freshness()
    elif args.clean_stale:
        clean_stale_data(args.days)
    elif args.reset_ticker:
        reset_ticker_data(args.reset_ticker)
    elif args.reset_all:
        reset_all_data(args.confirm)
    else:
        parser.print_help()
        print("\n示例:")
        print("  # 检查数据新鲜度")
        print("  python scripts/check_and_reset_candles.py --check")
        print()
        print("  # 清理超过30天的过时数据")
        print("  python scripts/check_and_reset_candles.py --clean-stale --days 30")
        print()
        print("  # 重置指定ticker")
        print("  python scripts/check_and_reset_candles.py --reset-ticker 000001")
