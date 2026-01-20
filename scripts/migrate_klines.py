#!/usr/bin/env python3
"""
K线数据迁移脚本 v2
将现有的 candles 表和 CSV 概念K线数据迁移到统一的 klines 表

优化:
- 使用批量 upsert 处理重复数据
- 添加进度显示
- 支持断点续传
"""

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.database import SessionLocal, engine, init_db
from src.models import (
    Candle,
    Kline,
    KlineTimeframe,
    SymbolType,
    DataUpdateLog,
    DataUpdateStatus,
    TradeCalendar,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

# 数据文件路径
DATA_DIR = Path(__file__).parent.parent / "data"
CONCEPT_DAILY_CSV = DATA_DIR / "concept_klines" / "concept_klines_daily.csv"
CONCEPT_30MIN_CSV = DATA_DIR / "concept_klines" / "concept_klines_30min.csv"

# 批量处理大小
BATCH_SIZE = 5000


def calculate_macd(
    close_prices: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> dict[str, list[float | None]]:
    """计算MACD指标"""
    if len(close_prices) < slow_period:
        return {
            "dif": [None] * len(close_prices),
            "dea": [None] * len(close_prices),
            "macd": [None] * len(close_prices),
        }

    closes = np.array(close_prices, dtype=float)

    def ema(data: np.ndarray, period: int) -> np.ndarray:
        result = np.zeros(len(data))
        multiplier = 2 / (period + 1)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = (data[i] - result[i-1]) * multiplier + result[i-1]
        return result

    ema_fast = ema(closes, fast_period)
    ema_slow = ema(closes, slow_period)
    dif = ema_fast - ema_slow
    dea = ema(dif, signal_period)
    macd_bar = (dif - dea) * 2

    return {
        "dif": [round(v, 4) for v in dif.tolist()],
        "dea": [round(v, 4) for v in dea.tolist()],
        "macd": [round(v, 4) for v in macd_bar.tolist()],
    }


def batch_upsert_klines(session, kline_dicts: list[dict]) -> int:
    """批量 upsert K线数据"""
    if not kline_dicts:
        return 0

    stmt = sqlite_insert(Kline).values(kline_dicts)
    stmt = stmt.on_conflict_do_update(
        index_elements=['symbol_type', 'symbol_code', 'timeframe', 'trade_time'],
        set_={
            'open': stmt.excluded.open,
            'high': stmt.excluded.high,
            'low': stmt.excluded.low,
            'close': stmt.excluded.close,
            'volume': stmt.excluded.volume,
            'amount': stmt.excluded.amount,
            'dif': stmt.excluded.dif,
            'dea': stmt.excluded.dea,
            'macd': stmt.excluded.macd,
            'symbol_name': stmt.excluded.symbol_name,
            'updated_at': datetime.now(timezone.utc),
        }
    )
    session.execute(stmt)
    session.commit()
    return len(kline_dicts)


def migrate_candles_to_klines(session) -> int:
    """迁移现有 candles 表数据到 klines 表"""
    logger.info("开始迁移 candles 表数据...")

    # 获取 candles 表记录数
    count_result = session.execute(text("SELECT COUNT(*) FROM candles")).scalar()
    logger.info(f"candles 表共有 {count_result} 条记录")

    if count_result == 0:
        return 0

    # 获取所有不同的 ticker
    tickers = session.execute(
        text("SELECT DISTINCT ticker FROM candles ORDER BY ticker")
    ).fetchall()
    logger.info(f"共有 {len(tickers)} 个不同的股票代码")

    total_migrated = 0

    for idx, (ticker,) in enumerate(tickers):
        # 获取该股票的所有 K线
        candles = session.query(Candle).filter(
            Candle.ticker == ticker
        ).order_by(Candle.timestamp).all()

        if not candles:
            continue

        # 按 timeframe 分组
        from collections import defaultdict
        by_timeframe = defaultdict(list)
        for candle in candles:
            by_timeframe[candle.timeframe.value].append(candle)

        for tf, candle_list in by_timeframe.items():
            # 计算 MACD
            closes = [float(c.close) for c in candle_list]
            macd_data = calculate_macd(closes)

            # 转换 timeframe
            timeframe_map = {
                "day": KlineTimeframe.DAY,
                "30m": KlineTimeframe.MINS_30,
                "week": KlineTimeframe.DAY,
                "month": KlineTimeframe.DAY,
            }
            kline_timeframe = timeframe_map.get(tf, KlineTimeframe.DAY)

            # 准备批量数据
            batch = []
            for i, candle in enumerate(candle_list):
                trade_time = candle.timestamp.strftime("%Y-%m-%d")
                if tf == "30m":
                    trade_time = candle.timestamp.strftime("%Y-%m-%d %H:%M:%S")

                batch.append({
                    'symbol_type': SymbolType.STOCK,
                    'symbol_code': ticker,
                    'symbol_name': None,
                    'timeframe': kline_timeframe,
                    'trade_time': trade_time,
                    'open': float(candle.open),
                    'high': float(candle.high),
                    'low': float(candle.low),
                    'close': float(candle.close),
                    'volume': float(candle.volume) if candle.volume else 0,
                    'amount': float(candle.turnover) if candle.turnover else 0,
                    'dif': macd_data["dif"][i],
                    'dea': macd_data["dea"][i],
                    'macd': macd_data["macd"][i],
                })

                if len(batch) >= BATCH_SIZE:
                    batch_upsert_klines(session, batch)
                    total_migrated += len(batch)
                    batch = []

            # 处理剩余数据
            if batch:
                batch_upsert_klines(session, batch)
                total_migrated += len(batch)

        if (idx + 1) % 100 == 0:
            logger.info(f"进度: {idx + 1}/{len(tickers)} 股票, 已迁移 {total_migrated} 条")

    logger.info(f"candles 表迁移完成，共迁移 {total_migrated} 条记录")
    return total_migrated


def migrate_concept_klines_from_csv(session) -> int:
    """从 CSV 文件迁移概念K线数据"""
    logger.info("开始迁移概念K线CSV数据...")
    total_migrated = 0

    # 迁移日线数据
    if CONCEPT_DAILY_CSV.exists():
        migrated = _migrate_csv_file(
            session,
            CONCEPT_DAILY_CSV,
            KlineTimeframe.DAY,
            is_daily=True
        )
        total_migrated += migrated
        logger.info(f"日线数据迁移完成: {migrated} 条")

    # 迁移30分钟数据
    if CONCEPT_30MIN_CSV.exists():
        migrated = _migrate_csv_file(
            session,
            CONCEPT_30MIN_CSV,
            KlineTimeframe.MINS_30,
            is_daily=False
        )
        total_migrated += migrated
        logger.info(f"30分钟数据迁移完成: {migrated} 条")

    return total_migrated


def _migrate_csv_file(session, csv_path: Path, timeframe: KlineTimeframe, is_daily: bool) -> int:
    """迁移单个CSV文件"""
    from collections import defaultdict

    logger.info(f"读取 {csv_path}...")

    # 读取CSV (使用 utf-8-sig 自动处理 BOM)
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    logger.info(f"读取到 {len(rows)} 行数据")

    if not rows:
        return 0

    # 按概念代码分组
    grouped = defaultdict(list)
    for row in rows:
        code = row.get("code", "")
        if code:
            grouped[code].append(row)

    total_migrated = 0

    for code, concept_rows in grouped.items():
        # 按时间排序 - CSV 中都是用 datetime 列
        concept_rows.sort(key=lambda r: r.get("datetime", "") or r.get("date", ""))

        # 获取概念名称
        concept_name = concept_rows[0].get("name", "") if concept_rows else ""

        # 计算 MACD
        closes = []
        for row in concept_rows:
            try:
                closes.append(float(row.get("close", 0)))
            except (ValueError, TypeError):
                closes.append(0)

        macd_data = calculate_macd(closes)

        # 准备批量数据
        batch = []
        for i, row in enumerate(concept_rows):
            try:
                # 解析时间 - CSV 中都是用 datetime 列
                raw_time = row.get("datetime", "") or row.get("date", "")

                if is_daily:
                    # 格式: YYYYMMDD -> YYYY-MM-DD
                    if len(raw_time) == 8 and raw_time.isdigit():
                        trade_time = f"{raw_time[:4]}-{raw_time[4:6]}-{raw_time[6:8]}"
                    else:
                        trade_time = raw_time
                else:
                    # 格式可能是 YYYY-MM-DD HH:MM:SS 或 Unix timestamp
                    if raw_time.isdigit():
                        dt = datetime.fromtimestamp(int(raw_time))
                        trade_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        trade_time = raw_time

                if not trade_time:
                    continue

                batch.append({
                    'symbol_type': SymbolType.CONCEPT,
                    'symbol_code': code,
                    'symbol_name': concept_name,
                    'timeframe': timeframe,
                    'trade_time': trade_time,
                    'open': float(row.get("open", 0)),
                    'high': float(row.get("high", 0)),
                    'low': float(row.get("low", 0)),
                    'close': float(row.get("close", 0)),
                    'volume': float(row.get("volume", 0)),
                    'amount': float(row.get("amount", 0)),
                    'dif': macd_data["dif"][i] if i < len(macd_data["dif"]) else None,
                    'dea': macd_data["dea"][i] if i < len(macd_data["dea"]) else None,
                    'macd': macd_data["macd"][i] if i < len(macd_data["macd"]) else None,
                })

                if len(batch) >= BATCH_SIZE:
                    batch_upsert_klines(session, batch)
                    total_migrated += len(batch)
                    batch = []

            except Exception as e:
                logger.warning(f"迁移概念 {code} 记录失败: {e}")
                continue

        # 处理剩余数据
        if batch:
            batch_upsert_klines(session, batch)
            total_migrated += len(batch)

    return total_migrated


def migrate_index_klines(session) -> int:
    """下载并迁移指数K线数据"""
    logger.info("开始下载指数K线数据...")

    from src.config import get_settings
    from src.services.tushare_client import TushareClient
    from datetime import timedelta
    import httpx
    import asyncio

    settings = get_settings()
    client = TushareClient(
        token=settings.tushare_token,
        points=settings.tushare_points,
        delay=settings.tushare_delay,
        max_retries=settings.tushare_max_retries
    )

    # 指数列表
    indices = [
        ("000001.SH", "上证指数"),
        ("399001.SZ", "深证成指"),
        ("399006.SZ", "创业板指"),
        ("000688.SH", "科创50"),
        ("899050.BJ", "北证50"),
    ]

    total_migrated = 0
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

    for ts_code, name in indices:
        logger.info(f"下载 {name} ({ts_code}) 日线数据...")
        try:
            df = client.fetch_index_daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df.empty:
                logger.warning(f"未获取到 {name} 数据")
                continue

            df = df.sort_values("trade_date", ascending=True)

            # 计算 MACD
            closes = df["close"].tolist()
            macd_data = calculate_macd(closes)

            # 准备批量数据
            batch = []
            for i, (_, row) in enumerate(df.iterrows()):
                trade_date = str(row["trade_date"])
                trade_time = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"

                batch.append({
                    'symbol_type': SymbolType.INDEX,
                    'symbol_code': ts_code,
                    'symbol_name': name,
                    'timeframe': KlineTimeframe.DAY,
                    'trade_time': trade_time,
                    'open': float(row["open"]),
                    'high': float(row["high"]),
                    'low': float(row["low"]),
                    'close': float(row["close"]),
                    'volume': float(row["vol"]) if row["vol"] else 0,
                    'amount': float(row["amount"]) if row["amount"] else 0,
                    'dif': macd_data["dif"][i],
                    'dea': macd_data["dea"][i],
                    'macd': macd_data["macd"][i],
                })

            if batch:
                batch_upsert_klines(session, batch)
                total_migrated += len(batch)
                logger.info(f"  {name}: {len(batch)} 条日线")

        except Exception as e:
            logger.error(f"下载 {name} 失败: {e}")

    # 下载30分钟数据 (使用 Sina API)
    logger.info("下载指数30分钟K线数据...")

    async def fetch_30m(ts_code: str, name: str) -> list[dict]:
        """异步获取30分钟K线"""
        code, market = ts_code.split(".")
        if market == "SH":
            sina_code = f"sh{code}"
        elif market == "SZ":
            sina_code = f"sz{code}"
        elif market == "BJ":
            sina_code = f"bj{code}"
        else:
            return []

        url = f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol={sina_code}&scale=30&datalen=240"

        try:
            async with httpx.AsyncClient() as http_client:
                resp = await http_client.get(url, headers={
                    "Referer": "http://finance.sina.com.cn/",
                    "User-Agent": "Mozilla/5.0"
                }, timeout=15.0)
                resp.raise_for_status()

                data = resp.json()
                if not data:
                    return []

                closes = [float(k["close"]) for k in data]
                macd_data = calculate_macd(closes)

                result = []
                for i, k in enumerate(data):
                    dt = datetime.strptime(k["day"], "%Y-%m-%d %H:%M:%S")
                    trade_time = dt.strftime("%Y-%m-%d %H:%M:%S")

                    result.append({
                        'symbol_type': SymbolType.INDEX,
                        'symbol_code': ts_code,
                        'symbol_name': name,
                        'timeframe': KlineTimeframe.MINS_30,
                        'trade_time': trade_time,
                        'open': float(k["open"]),
                        'high': float(k["high"]),
                        'low': float(k["low"]),
                        'close': float(k["close"]),
                        'volume': int(float(k["volume"])),
                        'amount': float(k["amount"]),
                        'dif': macd_data["dif"][i],
                        'dea': macd_data["dea"][i],
                        'macd': macd_data["macd"][i],
                    })

                return result
        except Exception as e:
            logger.error(f"获取 {name} 30分钟数据失败: {e}")
            return []

    async def fetch_all_30m():
        tasks = [fetch_30m(ts_code, name) for ts_code, name in indices]
        return await asyncio.gather(*tasks)

    results = asyncio.run(fetch_all_30m())

    for (ts_code, name), data in zip(indices, results):
        if data:
            batch_upsert_klines(session, data)
            total_migrated += len(data)
            logger.info(f"  {name}: {len(data)} 条30分钟线")

    logger.info(f"指数K线数据迁移完成，共 {total_migrated} 条")
    return total_migrated


def init_trade_calendar(session) -> int:
    """初始化交易日历"""
    logger.info("初始化交易日历...")

    try:
        from src.config import get_settings
        from src.services.tushare_client import TushareClient
        from datetime import timedelta

        settings = get_settings()
        client = TushareClient(
            token=settings.tushare_token,
            points=settings.tushare_points,
            delay=settings.tushare_delay,
            max_retries=settings.tushare_max_retries
        )

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        df = client.pro.trade_cal(
            exchange="SSE",
            start_date=start_date,
            end_date=end_date,
            fields="cal_date,is_open"
        )

        if df is None or df.empty:
            logger.warning("无法获取交易日历数据")
            return 0

        added = 0
        for _, row in df.iterrows():
            cal_date = str(row["cal_date"])
            is_open = row["is_open"] == 1
            date_str = f"{cal_date[:4]}-{cal_date[4:6]}-{cal_date[6:8]}"

            # 使用原生 SQL upsert
            session.execute(
                text("""
                    INSERT OR REPLACE INTO trade_calendar (date, is_trading_day, exchange, created_at)
                    VALUES (:date, :is_trading_day, :exchange, :created_at)
                """),
                {
                    "date": date_str,
                    "is_trading_day": 1 if is_open else 0,
                    "exchange": "SSE",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            added += 1

        session.commit()
        logger.info(f"交易日历初始化完成，添加 {added} 条记录")
        return added

    except Exception as e:
        logger.error(f"初始化交易日历失败: {e}")
        return 0


def log_update(session, update_type: str, status: DataUpdateStatus,
               records: int = 0, error: str = None):
    """记录更新日志"""
    now = datetime.now(timezone.utc)
    session.execute(
        text("""
            INSERT INTO data_update_log (update_type, status, records_updated, error_message, started_at, completed_at, created_at)
            VALUES (:update_type, :status, :records, :error, :started_at, :completed_at, :created_at)
        """),
        {
            "update_type": update_type,
            "status": status.value,
            "records": records,
            "error": error,
            "started_at": now.isoformat(),
            "completed_at": now.isoformat() if status != DataUpdateStatus.STARTED else None,
            "created_at": now.isoformat(),
        }
    )
    session.commit()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="K线数据迁移脚本")
    parser.add_argument("--skip-candles", action="store_true", help="跳过 candles 表迁移")
    parser.add_argument("--skip-concepts", action="store_true", help="跳过概念K线 CSV 迁移")
    parser.add_argument("--skip-indices", action="store_true", help="跳过指数K线下载")
    parser.add_argument("--skip-calendar", action="store_true", help="跳过交易日历初始化")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("K线数据迁移脚本启动 v2")
    logger.info("=" * 60)

    # 初始化数据库表
    logger.info("初始化数据库表...")
    init_db()

    session = SessionLocal()
    try:
        log_update(session, "migration", DataUpdateStatus.STARTED)

        total_migrated = 0

        # 1. 迁移 candles 表
        if not args.skip_candles:
            candles_migrated = migrate_candles_to_klines(session)
            total_migrated += candles_migrated
        else:
            logger.info("跳过 candles 表迁移")
            candles_migrated = 0

        # 2. 迁移概念K线 CSV
        if not args.skip_concepts:
            concept_migrated = migrate_concept_klines_from_csv(session)
            total_migrated += concept_migrated
        else:
            logger.info("跳过概念K线 CSV 迁移")
            concept_migrated = 0

        # 3. 下载指数K线
        if not args.skip_indices:
            index_migrated = migrate_index_klines(session)
            total_migrated += index_migrated
        else:
            logger.info("跳过指数K线下载")
            index_migrated = 0

        # 4. 初始化交易日历
        if not args.skip_calendar:
            calendar_added = init_trade_calendar(session)
        else:
            logger.info("跳过交易日历初始化")
            calendar_added = 0

        log_update(
            session,
            "migration",
            DataUpdateStatus.COMPLETED,
            records=total_migrated
        )

        logger.info("=" * 60)
        logger.info("迁移完成统计:")
        logger.info(f"  - candles 表: {candles_migrated} 条")
        logger.info(f"  - 概念K线 CSV: {concept_migrated} 条")
        logger.info(f"  - 指数K线: {index_migrated} 条")
        logger.info(f"  - 交易日历: {calendar_added} 条")
        logger.info(f"  - 总计: {total_migrated} 条K线数据")
        logger.info("=" * 60)

    except Exception as e:
        logger.exception("迁移失败")
        session.rollback()
        try:
            session2 = SessionLocal()
            log_update(session2, "migration", DataUpdateStatus.FAILED, error=str(e))
            session2.close()
        except:
            pass
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
