#!/usr/bin/env python3
"""
双源并行同步30分钟K线数据

使用新浪和东方财富两个数据源并行获取，分摊负载避免封IP
保守策略：每个源3秒间隔
"""
import sys
import os
import logging
import threading
from datetime import datetime, timezone

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import session_scope
from src.models import SymbolMetadata, Candle, Timeframe
from src.services.sina_kline_provider import SinaKlineProvider
from src.services.eastmoney_kline_provider import EastMoneyKlineProvider
from sqlalchemy import select

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
LOGGER = logging.getLogger(__name__)

# 配置
DELAY = 3.0  # 保守策略：3秒间隔
LIMIT = 500  # 每只股票获取500条K线


def get_all_tickers():
    """获取数据库中所有股票代码"""
    with session_scope() as session:
        tickers = session.execute(
            select(SymbolMetadata.ticker).order_by(SymbolMetadata.ticker)
        ).scalars().all()
    return list(tickers)


def save_klines_to_db(df, source_name: str):
    """保存K线数据到数据库"""
    if df is None or df.empty:
        LOGGER.warning(f"[{source_name}] 无数据需要保存")
        return 0

    count = 0
    with session_scope() as session:
        for _, row in df.iterrows():
            try:
                # 检查是否已存在
                existing = session.execute(
                    select(Candle).where(
                        Candle.ticker == row['ticker'],
                        Candle.timeframe == Timeframe.MINS_30,
                        Candle.timestamp == row['timestamp']
                    )
                ).scalar_one_or_none()

                if existing:
                    # 更新
                    existing.open = row['open']
                    existing.high = row['high']
                    existing.low = row['low']
                    existing.close = row['close']
                    existing.volume = row['volume']
                else:
                    # 插入
                    candle = Candle(
                        ticker=row['ticker'],
                        timeframe=Timeframe.MINS_30,
                        timestamp=row['timestamp'],
                        open=row['open'],
                        high=row['high'],
                        low=row['low'],
                        close=row['close'],
                        volume=row['volume']
                    )
                    session.add(candle)

                count += 1

                # 每1000条提交一次
                if count % 1000 == 0:
                    session.commit()
                    LOGGER.info(f"[{source_name}] 已保存 {count} 条K线")

            except Exception as e:
                LOGGER.warning(f"[{source_name}] 保存失败 {row['ticker']}: {e}")
                continue

        session.commit()

    LOGGER.info(f"[{source_name}] 保存完成，共 {count} 条K线")
    return count


def sync_with_sina(tickers: list, results: dict):
    """使用新浪源同步"""
    LOGGER.info(f"[新浪] 开始同步 {len(tickers)} 只股票")
    provider = SinaKlineProvider(delay=DELAY)

    def progress(current, total, ticker):
        if current % 50 == 0:
            print(f"[新浪] {current}/{total} - {ticker}")

    df = provider.fetch_batch(tickers, period="30m", limit=LIMIT, progress_callback=progress)
    count = save_klines_to_db(df, "新浪")
    results['sina'] = {'tickers': len(tickers), 'klines': count}
    LOGGER.info(f"[新浪] 完成! {len(tickers)} 只股票, {count} 条K线")


def sync_with_eastmoney(tickers: list, results: dict):
    """使用东方财富源同步"""
    LOGGER.info(f"[东财] 开始同步 {len(tickers)} 只股票")
    provider = EastMoneyKlineProvider(delay=DELAY)

    def progress(current, total, ticker):
        if current % 50 == 0:
            print(f"[东财] {current}/{total} - {ticker}")

    df = provider.fetch_batch(tickers, period="30m", limit=LIMIT, progress_callback=progress)
    count = save_klines_to_db(df, "东财")
    results['eastmoney'] = {'tickers': len(tickers), 'klines': count}
    LOGGER.info(f"[东财] 完成! {len(tickers)} 只股票, {count} 条K线")


def main():
    start_time = datetime.now()
    LOGGER.info("=" * 60)
    LOGGER.info("开始双源并行同步30分钟K线数据")
    LOGGER.info(f"保守策略: {DELAY}秒/请求")
    LOGGER.info("=" * 60)

    # 获取所有股票
    all_tickers = get_all_tickers()
    total = len(all_tickers)
    LOGGER.info(f"共 {total} 只股票")

    # 分成两组
    mid = total // 2
    sina_tickers = all_tickers[:mid]
    eastmoney_tickers = all_tickers[mid:]

    LOGGER.info(f"新浪负责: {len(sina_tickers)} 只")
    LOGGER.info(f"东财负责: {len(eastmoney_tickers)} 只")

    # 预估时间
    estimated_minutes = max(len(sina_tickers), len(eastmoney_tickers)) * DELAY / 60
    LOGGER.info(f"预计耗时: {estimated_minutes:.0f} 分钟")

    # 并行执行
    results = {}

    sina_thread = threading.Thread(
        target=sync_with_sina,
        args=(sina_tickers, results)
    )
    eastmoney_thread = threading.Thread(
        target=sync_with_eastmoney,
        args=(eastmoney_tickers, results)
    )

    sina_thread.start()
    eastmoney_thread.start()

    sina_thread.join()
    eastmoney_thread.join()

    # 汇总结果
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds() / 60

    LOGGER.info("=" * 60)
    LOGGER.info("同步完成!")
    LOGGER.info(f"耗时: {duration:.1f} 分钟")
    LOGGER.info(f"新浪: {results.get('sina', {})}")
    LOGGER.info(f"东财: {results.get('eastmoney', {})}")

    total_klines = sum(r.get('klines', 0) for r in results.values())
    LOGGER.info(f"总计: {total_klines} 条K线")
    LOGGER.info("=" * 60)


if __name__ == "__main__":
    main()
