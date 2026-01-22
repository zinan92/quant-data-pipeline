"""
统一K线数据服务 - 重构版本

提供统一的K线数据访问接口，使用Repository模式。
业务逻辑层，专注于指标计算和数据组装。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.models import KlineTimeframe, SymbolType
from src.repositories.kline_repository import KlineRepository
from src.repositories.symbol_repository import SymbolRepository
from src.schemas.normalized import NormalizedDate, NormalizedTicker
from src.utils.indicators import calculate_macd
from src.utils.logging import get_logger

logger = get_logger(__name__)


class KlineService:
    """
    K线数据业务服务

    职责:
    - 查询K线数据（委托给Repository）
    - 计算技术指标（MACD等）
    - 组装返回数据格式
    """

    def __init__(
        self,
        kline_repo: KlineRepository,
        symbol_repo: Optional[SymbolRepository] = None,
    ):
        """
        初始化KlineService

        Args:
            kline_repo: K线数据Repository
            symbol_repo: 标的数据Repository（可选）
        """
        self.kline_repo = kline_repo
        self.symbol_repo = symbol_repo

    @classmethod
    def create_with_session(cls, session: Session) -> "KlineService":
        """
        使用Session创建KlineService实例（工厂方法）

        Args:
            session: SQLAlchemy Session

        Returns:
            KlineService实例
        """
        kline_repo = KlineRepository(session)
        symbol_repo = SymbolRepository(session)
        return cls(kline_repo, symbol_repo)

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
        start_datetime = None
        end_datetime = None

        if start_date:
            try:
                start_datetime = datetime.fromisoformat(
                    NormalizedDate(value=start_date).to_iso()
                )
            except ValueError:
                pass

        if end_date:
            try:
                end_datetime = datetime.fromisoformat(
                    NormalizedDate(value=end_date).to_iso()
                )
            except ValueError:
                pass

        # 根据是否有日期范围选择不同的查询方法
        if start_datetime and end_datetime:
            klines = self.kline_repo.find_by_symbol_and_date_range(
                symbol_code=symbol_code,
                symbol_type=symbol_type,
                timeframe=timeframe,
                start_date=start_datetime,
                end_date=end_datetime,
            )
        else:
            klines = self.kline_repo.find_by_symbol(
                symbol_code=symbol_code,
                symbol_type=symbol_type,
                timeframe=timeframe,
                limit=limit,
            )
            # Repository返回的是倒序，需要反转
            klines = list(reversed(klines))

        # 转换为字典格式
        return [
            {
                "datetime": k.trade_time,  # Return as 'datetime' for API backward compatibility
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "volume": k.volume,
                "amount": k.amount,
            }
            for k in klines
        ]

    def get_klines_with_indicators(
        self,
        symbol_type: SymbolType,
        symbol_code: str,
        timeframe: KlineTimeframe = KlineTimeframe.DAY,
        limit: int = 120,
        include_macd: bool = True,
    ) -> list[dict]:
        """
        获取带技术指标的K线数据

        Args:
            symbol_type: 标的类型
            symbol_code: 标的代码
            timeframe: 时间周期
            limit: 返回数量
            include_macd: 是否包含MACD指标

        Returns:
            包含技术指标的K线数据列表
        """
        klines = self.get_klines(symbol_type, symbol_code, timeframe, limit)

        if not klines:
            return []

        # 计算MACD指标
        if include_macd:
            close_prices = [k["close"] for k in klines if k["close"] is not None]
            if close_prices:
                macd_data = calculate_macd(close_prices)

                # 将指标添加到K线数据中
                for i, kline in enumerate(klines):
                    if i < len(macd_data["dif"]):
                        kline["dif"] = macd_data["dif"][i]
                        kline["dea"] = macd_data["dea"][i]
                        kline["macd"] = macd_data["macd"][i]

        return klines

    def get_klines_with_meta(
        self,
        symbol_type: SymbolType,
        symbol_code: str,
        timeframe: KlineTimeframe = KlineTimeframe.DAY,
        limit: int = 120,
        include_indicators: bool = True,
    ) -> dict:
        """
        获取K线数据及元信息

        Args:
            symbol_type: 标的类型
            symbol_code: 标的代码
            timeframe: 时间周期
            limit: 返回数量
            include_indicators: 是否包含技术指标

        Returns:
            包含 symbol_type, symbol_code, symbol_name, timeframe, count, klines 的字典
        """
        # 获取K线数据
        if include_indicators:
            klines = self.get_klines_with_indicators(
                symbol_type, symbol_code, timeframe, limit
            )
        else:
            klines = self.get_klines(symbol_type, symbol_code, timeframe, limit)

        # 获取标的名称
        symbol_name = None
        if klines:
            # 从第一条K线获取名称
            first_kline = self.kline_repo.find_by_symbol(
                symbol_code=symbol_code,
                symbol_type=symbol_type,
                timeframe=timeframe,
                limit=1,
            )
            if first_kline:
                symbol_name = first_kline[0].symbol_name

        return {
            "symbol_type": symbol_type.value,
            "symbol_code": symbol_code,
            "symbol_name": symbol_name,
            "timeframe": timeframe.value,
            "count": len(klines),
            "klines": klines,
        }

    def get_latest_kline(
        self,
        symbol_type: SymbolType,
        symbol_code: str,
        timeframe: KlineTimeframe = KlineTimeframe.DAY,
    ) -> Optional[dict]:
        """
        获取最新的K线数据

        Args:
            symbol_type: 标的类型
            symbol_code: 标的代码
            timeframe: 时间周期

        Returns:
            最新K线数据字典或None
        """
        kline = self.kline_repo.find_latest_by_symbol(
            symbol_code=symbol_code,
            symbol_type=symbol_type,
            timeframe=timeframe,
        )

        if not kline:
            return None

        return {
            "datetime": kline.trade_time,  # Return as 'datetime' for API backward compatibility
            "open": kline.open,
            "high": kline.high,
            "low": kline.low,
            "close": kline.close,
            "volume": kline.volume,
            "amount": kline.amount,
        }

    def get_latest_trade_time(
        self,
        symbol_type: SymbolType,
        symbol_code: str,
        timeframe: KlineTimeframe = KlineTimeframe.DAY,
    ) -> Optional[str]:
        """
        获取最新K线时间

        Args:
            symbol_type: 标的类型
            symbol_code: 标的代码
            timeframe: 时间周期

        Returns:
            最新交易时间的ISO字符串或None
        """
        kline = self.kline_repo.find_latest_by_symbol(
            symbol_code, symbol_type, timeframe
        )

        if kline and kline.trade_time:
            return kline.trade_time

        return None

    def get_klines_count(
        self,
        symbol_type: SymbolType,
        symbol_code: str,
        timeframe: KlineTimeframe = KlineTimeframe.DAY,
    ) -> int:
        """
        获取K线数据数量

        Args:
            symbol_type: 标的类型
            symbol_code: 标的代码
            timeframe: 时间周期

        Returns:
            K线数量
        """
        return self.kline_repo.count_by_symbol(symbol_code, symbol_type, timeframe)

    def get_symbols_with_kline_data(
        self,
        symbol_type: SymbolType,
        timeframe: KlineTimeframe = KlineTimeframe.DAY,
    ) -> list[str]:
        """
        获取有K线数据的标的列表

        Args:
            symbol_type: 标的类型
            timeframe: 时间周期

        Returns:
            标的代码列表
        """
        return self.kline_repo.find_symbols_with_data(symbol_type, timeframe)

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
        from src.models import Kline
        from src.schemas.normalized import NormalizedDateTime

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

            now = datetime.now(timezone.utc)
            records.append(
                Kline(
                    symbol_type=symbol_type,
                    symbol_code=symbol_code,
                    symbol_name=symbol_name,
                    timeframe=timeframe,
                    trade_time=trade_time,
                    open=float(k.get("open", 0)),
                    high=float(k.get("high", 0)),
                    low=float(k.get("low", 0)),
                    close=float(k.get("close", 0)),
                    volume=float(k.get("volume", 0)),
                    amount=float(k.get("amount", 0)),
                    dif=macd_data["dif"][i],
                    dea=macd_data["dea"][i],
                    macd=macd_data["macd"][i],
                    created_at=now,
                    updated_at=now,
                )
            )

        # 使用repository保存
        return self.kline_repo.upsert_batch(records)
