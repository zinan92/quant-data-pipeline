"""
统一K线数据服务
提供统一的K线数据访问接口，支持个股、指数、概念板块
"""

from datetime import datetime, timezone
from typing import Optional

import numpy as np
from sqlalchemy import and_, desc
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.models import Kline, KlineTimeframe, SymbolType
from src.schemas.normalized import NormalizedDate, NormalizedDateTime, NormalizedTicker
from src.utils.logging import get_logger

logger = get_logger(__name__)


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


class KlineService:
    """统一K线数据服务"""

    def __init__(self, session: Optional[Session] = None):
        self._session = session
        self._owns_session = session is None

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = SessionLocal()
        return self._session

    def close(self):
        if self._owns_session and self._session is not None:
            self._session.close()
            self._session = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_klines(
        self,
        symbol_type: SymbolType,
        symbol_code: str,
        timeframe: KlineTimeframe = KlineTimeframe.DAY,
        limit: int = 120,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """
        获取K线数据

        Args:
            symbol_type: 标的类型 (stock/index/concept)
            symbol_code: 标的代码 (支持任意格式，会自动标准化)
            timeframe: 时间周期 (day/30m)
            limit: 返回数量
            start_date: 开始日期 (可选，支持任意格式)
            end_date: 结束日期 (可选，支持任意格式)

        Returns:
            K线数据列表，日期格式为ISO标准 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
        """
        # 标准化symbol_code（个股用6位代码，指数/概念保持原样）
        if symbol_type == SymbolType.STOCK:
            try:
                symbol_code = NormalizedTicker(raw=symbol_code).raw
            except ValueError:
                pass  # 保持原值

        # 标准化日期参数
        if start_date:
            try:
                start_date = NormalizedDate(value=start_date).to_iso()
            except ValueError:
                pass
        if end_date:
            try:
                end_date = NormalizedDate(value=end_date).to_iso()
            except ValueError:
                pass

        query = self.session.query(Kline).filter(
            and_(
                Kline.symbol_type == symbol_type,
                Kline.symbol_code == symbol_code,
                Kline.timeframe == timeframe,
            )
        )

        if start_date:
            query = query.filter(Kline.trade_time >= start_date)
        if end_date:
            query = query.filter(Kline.trade_time <= end_date)

        # 按时间降序获取最新的 limit 条，然后再按时间升序排列
        klines = query.order_by(desc(Kline.trade_time)).limit(limit).all()
        klines = list(reversed(klines))

        return [
            {
                "datetime": k.trade_time,
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "volume": k.volume,
                "amount": k.amount,
                "dif": k.dif,
                "dea": k.dea,
                "macd": k.macd,
            }
            for k in klines
        ]

    def get_klines_with_meta(
        self,
        symbol_type: SymbolType,
        symbol_code: str,
        timeframe: KlineTimeframe = KlineTimeframe.DAY,
        limit: int = 120,
    ) -> dict:
        """
        获取K线数据及元信息

        Returns:
            包含 symbol_type, symbol_code, symbol_name, timeframe, count, klines 的字典
        """
        klines = self.get_klines(symbol_type, symbol_code, timeframe, limit)

        # 获取名称
        first_kline = self.session.query(Kline).filter(
            and_(
                Kline.symbol_type == symbol_type,
                Kline.symbol_code == symbol_code,
            )
        ).first()

        symbol_name = first_kline.symbol_name if first_kline else None

        return {
            "symbol_type": symbol_type.value,
            "symbol_code": symbol_code,
            "symbol_name": symbol_name,
            "timeframe": timeframe.value,
            "count": len(klines),
            "klines": klines,
        }

    def get_latest_trade_time(
        self,
        symbol_type: SymbolType,
        symbol_code: str,
        timeframe: KlineTimeframe = KlineTimeframe.DAY,
    ) -> Optional[str]:
        """获取最新K线时间"""
        kline = self.session.query(Kline).filter(
            and_(
                Kline.symbol_type == symbol_type,
                Kline.symbol_code == symbol_code,
                Kline.timeframe == timeframe,
            )
        ).order_by(desc(Kline.trade_time)).first()

        return kline.trade_time if kline else None

    def save_klines(
        self,
        symbol_type: SymbolType,
        symbol_code: str,
        symbol_name: Optional[str],
        timeframe: KlineTimeframe,
        klines: list[dict],
        calculate_indicators: bool = True,
    ) -> int:
        """
        保存K线数据 (upsert)

        Args:
            symbol_type: 标的类型
            symbol_code: 标的代码 (会自动标准化)
            symbol_name: 标的名称
            timeframe: 时间周期
            klines: K线数据列表，每个包含 datetime, open, high, low, close, volume, amount
            calculate_indicators: 是否计算 MACD 指标

        Returns:
            保存的记录数
        """
        if not klines:
            return 0

        # 标准化symbol_code（个股用6位代码）
        if symbol_type == SymbolType.STOCK:
            try:
                symbol_code = NormalizedTicker(raw=symbol_code).raw
            except ValueError:
                pass

        # 按时间排序
        klines = sorted(klines, key=lambda k: k.get("datetime", ""))

        # 计算 MACD
        if calculate_indicators:
            closes = [float(k.get("close", 0)) for k in klines]
            macd_data = calculate_macd(closes)
        else:
            macd_data = {"dif": [None] * len(klines), "dea": [None] * len(klines), "macd": [None] * len(klines)}

        # 准备数据，标准化日期格式
        is_daily = timeframe == KlineTimeframe.DAY
        records = []
        for i, k in enumerate(klines):
            raw_time = k.get("datetime", "")
            # 标准化日期时间
            try:
                if is_daily:
                    trade_time = NormalizedDate(value=raw_time).to_iso()
                else:
                    trade_time = NormalizedDateTime(value=raw_time).to_iso()
            except ValueError:
                trade_time = raw_time  # 保持原值

            records.append({
                "symbol_type": symbol_type,
                "symbol_code": symbol_code,
                "symbol_name": symbol_name,
                "timeframe": timeframe,
                "trade_time": trade_time,
                "open": float(k.get("open", 0)),
                "high": float(k.get("high", 0)),
                "low": float(k.get("low", 0)),
                "close": float(k.get("close", 0)),
                "volume": float(k.get("volume", 0)),
                "amount": float(k.get("amount", 0)),
                "dif": k.get("dif") or macd_data["dif"][i],
                "dea": k.get("dea") or macd_data["dea"][i],
                "macd": k.get("macd") or macd_data["macd"][i],
            })

        # 批量 upsert
        stmt = sqlite_insert(Kline).values(records)
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
            }
        )
        self.session.execute(stmt)
        self.session.commit()

        return len(records)

    def delete_old_klines(
        self,
        symbol_type: SymbolType,
        timeframe: KlineTimeframe,
        before_date: str,
    ) -> int:
        """
        删除旧的K线数据

        Args:
            symbol_type: 标的类型
            timeframe: 时间周期
            before_date: 删除此日期之前的数据

        Returns:
            删除的记录数
        """
        result = self.session.query(Kline).filter(
            and_(
                Kline.symbol_type == symbol_type,
                Kline.timeframe == timeframe,
                Kline.trade_time < before_date,
            )
        ).delete()

        self.session.commit()
        return result


# 便捷函数
def get_stock_klines(symbol_code: str, timeframe: str = "day", limit: int = 120) -> dict:
    """获取个股K线"""
    tf = KlineTimeframe.DAY if timeframe == "day" else KlineTimeframe.MINS_30
    with KlineService() as service:
        return service.get_klines_with_meta(SymbolType.STOCK, symbol_code, tf, limit)


def get_index_klines(symbol_code: str, timeframe: str = "day", limit: int = 120) -> dict:
    """获取指数K线"""
    tf = KlineTimeframe.DAY if timeframe == "day" else KlineTimeframe.MINS_30
    with KlineService() as service:
        return service.get_klines_with_meta(SymbolType.INDEX, symbol_code, tf, limit)


def get_concept_klines(symbol_code: str, timeframe: str = "day", limit: int = 120) -> dict:
    """获取概念K线"""
    tf = KlineTimeframe.DAY if timeframe == "day" else KlineTimeframe.MINS_30
    with KlineService() as service:
        return service.get_klines_with_meta(SymbolType.CONCEPT, symbol_code, tf, limit)
