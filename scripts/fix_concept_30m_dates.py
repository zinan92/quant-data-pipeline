#!/usr/bin/env python3
"""
修复概念30分钟K线的错误日期

问题: 迁移脚本错误地将 YYYYMMDDHHMM (如 202512291430) 当作 Unix timestamp 处理，
导致日期变成了 8390 年。

解决方案:
1. 删除所有错误的概念30分钟数据
2. 从原始CSV重新导入，使用标准化模型确保格式正确
"""

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import and_, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.database import SessionLocal, engine
from src.models import Kline, KlineTimeframe, SymbolType
from src.schemas.normalized import NormalizedDateTime, NormalizedKline
from src.utils.logging import get_logger

logger = get_logger(__name__)

# 数据文件路径
DATA_DIR = Path(__file__).parent.parent / "data"
CONCEPT_30MIN_CSV = DATA_DIR / "concept_klines" / "concept_klines_30min.csv"

# 批量处理大小
BATCH_SIZE = 1000


def calculate_macd(
    close_prices: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, list[float | None]]:
    """计算MACD指标"""
    import numpy as np

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
            result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
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


def delete_bad_concept_30m_data(session) -> int:
    """删除所有错误的概念30分钟数据"""
    logger.info("删除错误的概念30分钟数据...")

    # 删除所有概念30分钟数据（因为都是错误的）
    result = session.execute(
        text("""
            DELETE FROM klines
            WHERE symbol_type = 'CONCEPT'
            AND timeframe = 'MINS_30'
        """)
    )
    session.commit()

    deleted = result.rowcount
    logger.info(f"删除了 {deleted} 条错误数据")
    return deleted


def reimport_concept_30m_from_csv(session) -> int:
    """从CSV重新导入概念30分钟数据，使用标准化模型"""
    if not CONCEPT_30MIN_CSV.exists():
        logger.error(f"CSV文件不存在: {CONCEPT_30MIN_CSV}")
        return 0

    logger.info(f"从CSV重新导入: {CONCEPT_30MIN_CSV}")

    # 读取CSV
    with open(CONCEPT_30MIN_CSV, "r", encoding="utf-8-sig") as f:
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

    total_imported = 0

    for code, concept_rows in grouped.items():
        # 按时间排序
        concept_rows.sort(key=lambda r: r.get("datetime", ""))

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
                raw_time = row.get("datetime", "")
                if not raw_time:
                    continue

                # 使用标准化模型解析时间
                # CSV格式: YYYYMMDDHHMM (如 202512291430)
                try:
                    normalized_dt = NormalizedDateTime(value=raw_time)
                    trade_time = normalized_dt.to_iso()
                except ValueError as e:
                    logger.warning(f"无法解析时间 {raw_time}: {e}")
                    continue

                batch.append(
                    {
                        "symbol_type": SymbolType.CONCEPT,
                        "symbol_code": code,
                        "symbol_name": concept_name,
                        "timeframe": KlineTimeframe.MINS_30,
                        "trade_time": trade_time,
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": float(row.get("volume", 0)),
                        "amount": float(row.get("amount", 0)),
                        "dif": macd_data["dif"][i] if i < len(macd_data["dif"]) else None,
                        "dea": macd_data["dea"][i] if i < len(macd_data["dea"]) else None,
                        "macd": macd_data["macd"][i]
                        if i < len(macd_data["macd"])
                        else None,
                    }
                )

                if len(batch) >= BATCH_SIZE:
                    _batch_insert(session, batch)
                    total_imported += len(batch)
                    batch = []

            except Exception as e:
                logger.warning(f"处理概念 {code} 记录失败: {e}")
                continue

        # 处理剩余数据
        if batch:
            _batch_insert(session, batch)
            total_imported += len(batch)

    logger.info(f"重新导入完成，共 {total_imported} 条")
    return total_imported


def _batch_insert(session, kline_dicts: list[dict]) -> int:
    """批量插入K线数据"""
    if not kline_dicts:
        return 0

    stmt = sqlite_insert(Kline).values(kline_dicts)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol_type", "symbol_code", "timeframe", "trade_time"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "amount": stmt.excluded.amount,
            "dif": stmt.excluded.dif,
            "dea": stmt.excluded.dea,
            "macd": stmt.excluded.macd,
            "symbol_name": stmt.excluded.symbol_name,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    session.execute(stmt)
    session.commit()
    return len(kline_dicts)


def verify_data(session) -> bool:
    """验证修复后的数据"""
    logger.info("验证数据...")

    # 检查是否还有错误日期
    result = session.execute(
        text("""
            SELECT COUNT(*) FROM klines
            WHERE symbol_type = 'CONCEPT'
            AND timeframe = 'MINS_30'
            AND trade_time > '2100-01-01'
        """)
    )
    bad_count = result.scalar()

    if bad_count > 0:
        logger.error(f"仍有 {bad_count} 条错误数据！")
        return False

    # 检查数据范围
    result = session.execute(
        text("""
            SELECT MIN(trade_time), MAX(trade_time), COUNT(*)
            FROM klines
            WHERE symbol_type = 'CONCEPT'
            AND timeframe = 'MINS_30'
        """)
    )
    row = result.fetchone()
    min_time, max_time, count = row

    logger.info(f"数据范围: {min_time} ~ {max_time}, 共 {count} 条")

    # 抽查几条数据
    result = session.execute(
        text("""
            SELECT symbol_code, trade_time, close
            FROM klines
            WHERE symbol_type = 'CONCEPT'
            AND timeframe = 'MINS_30'
            ORDER BY trade_time DESC
            LIMIT 5
        """)
    )
    logger.info("最新5条数据:")
    for row in result:
        logger.info(f"  {row[0]}: {row[1]} = {row[2]}")

    return True


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("修复概念30分钟K线日期脚本")
    logger.info("=" * 60)

    session = SessionLocal()
    try:
        # 1. 删除错误数据
        deleted = delete_bad_concept_30m_data(session)

        # 2. 重新导入
        imported = reimport_concept_30m_from_csv(session)

        # 3. 验证
        success = verify_data(session)

        logger.info("=" * 60)
        logger.info("修复完成:")
        logger.info(f"  - 删除错误数据: {deleted} 条")
        logger.info(f"  - 重新导入: {imported} 条")
        logger.info(f"  - 验证结果: {'通过' if success else '失败'}")
        logger.info("=" * 60)

    except Exception as e:
        logger.exception(f"修复失败: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
