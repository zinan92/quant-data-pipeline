"""
Tushare Data Provider
提供与 AkshareDataProvider 兼容的接口，使用 Tushare Pro 作为数据源
"""

from datetime import datetime, timezone
from typing import Iterable, List

import pandas as pd

from src.config import Settings, get_settings
from src.models import Timeframe
from src.services.tushare_client import TushareClient
from src.utils.logging import LOGGER
from src.utils.ticker_utils import TickerNormalizer


class TushareDataProvider:
    """
    Tushare Pro 数据提供者

    提供与 AkshareDataProvider 兼容的接口，无缝替换 AkShare
    """

    _TIMEFRAME_TO_METHOD = {
        Timeframe.DAY: "daily",
        Timeframe.WEEK: "weekly",
        Timeframe.MONTH: "monthly",
        Timeframe.MINS_30: "mins",  # 30分钟K线
    }

    def __init__(self, settings: Settings | None = None) -> None:
        """
        初始化 TushareDataProvider

        Args:
            settings: 应用配置（未提供时自动加载）
        """
        self.settings = settings or get_settings()

        # 初始化 Tushare 客户端
        self.client = TushareClient(
            token=self.settings.tushare_token,
            points=self.settings.tushare_points,
            delay=self.settings.tushare_delay,
            max_retries=self.settings.tushare_max_retries
        )

        LOGGER.info(
            "TushareDataProvider 已初始化 (积分: %d, 延迟: %.2f秒)",
            self.settings.tushare_points,
            self.settings.tushare_delay
        )

    def fetch_candles(
        self,
        ticker: str,
        timeframe: Timeframe,
        limit: int
    ) -> pd.DataFrame:
        """
        获取 K 线数据

        Args:
            ticker: 股票代码（6位，如 000001）
            timeframe: 时间框架（DAY/WEEK/MONTH）
            limit: 返回的 K 线数量

        Returns:
            DataFrame: 包含以下列的数据
                - timestamp: datetime (UTC)
                - open, high, low, close: float
                - volume: float (手)
                - turnover: float (元)
                - ma5, ma10, ma20, ma50: float (移动平均线)

        Raises:
            ValueError: 无数据时抛出
        """
        # 标准化股票代码
        ticker = TickerNormalizer.normalize(ticker)
        ts_code = self.client.normalize_ts_code(ticker)

        LOGGER.info(
            "获取K线数据 | ticker=%s timeframe=%s limit=%s",
            ticker,
            timeframe.value,
            limit
        )

        # 计算日期范围（确保获取足够的数据）
        end_date = datetime.now().strftime('%Y%m%d')

        if timeframe == Timeframe.MINS_30:
            # 30分钟K线：每天约8根K线（4小时交易时间），所以需要 limit/8 天的数据
            days_needed = max(limit // 8 + 10, 30)  # 至少30天
        elif timeframe == Timeframe.DAY:
            days_needed = limit * 2
        else:
            days_needed = limit * 14

        start_date = (datetime.now() - pd.Timedelta(days=days_needed)).strftime('%Y%m%d')

        # 根据时间框架调用不同的接口
        method_name = self._TIMEFRAME_TO_METHOD[timeframe]
        fetch_method = getattr(self.client, f"fetch_{method_name}")

        if timeframe == Timeframe.MINS_30:
            # 30分钟K线使用特殊参数
            raw_df = fetch_method(
                ts_code=ts_code,
                freq="30min",
                start_date=start_date,
                end_date=end_date
            )
        else:
            raw_df = fetch_method(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

        if raw_df.empty:
            raise ValueError(f"没有获取到 {ticker} ({timeframe}) 的K线数据")

        # 数据格式转换
        frame = self._normalize_candle_data(raw_df, limit, is_mins=timeframe == Timeframe.MINS_30)

        LOGGER.debug(
            "获取到 %d 根K线 (请求: %d 根)",
            len(frame),
            limit
        )

        return frame

    def fetch_candles_since(
        self,
        ticker: str,
        timeframe: Timeframe,
        since_date: datetime
    ) -> pd.DataFrame:
        """
        获取指定日期之后的K线数据（增量更新）

        Args:
            ticker: 股票代码（6位，如 000001）
            timeframe: 时间框架（DAY/WEEK/MONTH）
            since_date: 起始日期（仅获取此日期之后的数据）

        Returns:
            DataFrame: 标准化的 K 线数据，如果没有新数据则返回空DataFrame

        Raises:
            ValueError: API调用失败时抛出
        """
        # 标准化股票代码
        ticker = TickerNormalizer.normalize(ticker)
        ts_code = self.client.normalize_ts_code(ticker)

        start_date = since_date.strftime('%Y%m%d')
        end_date = datetime.now().strftime('%Y%m%d')

        LOGGER.info(
            "获取增量K线数据 | ticker=%s timeframe=%s since=%s",
            ticker,
            timeframe.value,
            start_date
        )

        # 根据时间框架调用不同的接口
        method_name = self._TIMEFRAME_TO_METHOD[timeframe]
        fetch_method = getattr(self.client, f"fetch_{method_name}")

        raw_df = fetch_method(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date
        )

        if raw_df.empty:
            LOGGER.debug("没有新的K线数据 | ticker=%s timeframe=%s", ticker, timeframe.value)
            return pd.DataFrame()

        # 数据格式转换（不限制数量，返回所有新数据）
        frame = self._normalize_candle_data(raw_df, limit=None)

        # 过滤掉 <= since_date 的数据（因为API可能返回重复的起始日期数据）
        # 确保时区一致：将since_date转换为UTC时区
        if since_date.tzinfo is None:
            # 如果since_date是naive的，假设它是UTC
            since_date_utc = since_date.replace(tzinfo=timezone.utc)
        else:
            # 如果已经有时区，转换为UTC
            since_date_utc = since_date.astimezone(timezone.utc)
        frame = frame[frame['timestamp'] > since_date_utc]

        LOGGER.debug(
            "获取到 %d 根增量K线 | ticker=%s timeframe=%s",
            len(frame),
            ticker,
            timeframe.value
        )

        return frame

    def _normalize_candle_data(self, raw_df: pd.DataFrame, limit: int | None, is_mins: bool = False) -> pd.DataFrame:
        """
        将 Tushare 原始数据转换为标准格式

        Args:
            raw_df: Tushare 返回的原始数据
            limit: 限制返回的行数
            is_mins: 是否为分钟级数据

        Returns:
            DataFrame: 标准化后的 K 线数据
        """
        # 重命名字段（分钟级数据使用 trade_time，日线数据使用 trade_date）
        if is_mins:
            frame = raw_df.rename(columns={
                'trade_time': 'timestamp',
                'vol': 'volume',        # 成交量（手）
                'amount': 'turnover'    # 成交额（千元）
            }).copy()
            # 分钟级时间格式: 2024-01-15 10:00:00
            frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True)
        else:
            frame = raw_df.rename(columns={
                'trade_date': 'timestamp',
                'vol': 'volume',        # 成交量（手）
                'amount': 'turnover'    # 成交额（千元）
            }).copy()
            # 日线时间格式: YYYYMMDD
            frame['timestamp'] = pd.to_datetime(frame['timestamp'], format='%Y%m%d', utc=True)

        # Tushare 的 amount 单位是千元，转换为元
        if 'turnover' in frame.columns:
            frame['turnover'] = frame['turnover'] * 1000

        # 按时间升序排序，取最近的 limit 条（如果limit为None则返回全部）
        frame = frame.sort_values('timestamp', ascending=True)
        if limit is not None:
            frame = frame.tail(limit)
        frame = frame.reset_index(drop=True)

        # 计算移动平均线
        for window in (5, 10, 20, 50):
            frame[f'ma{window}'] = (
                frame['close'].rolling(window=window, min_periods=1).mean()
            )

        # 确保数值列类型正确
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'turnover']
        for col in numeric_cols:
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col], errors='coerce')

        # 选择需要的列（保持与 AkshareDataProvider 一致）
        required_cols = [
            'timestamp', 'open', 'high', 'low', 'close',
            'volume', 'turnover', 'ma5', 'ma10', 'ma20', 'ma50'
        ]

        return frame[required_cols]

    def fetch_symbol_metadata(self, tickers: Iterable[str]) -> pd.DataFrame:
        """
        获取股票元数据

        Args:
            tickers: 股票代码列表

        Returns:
            DataFrame: 包含以下列的元数据
                - ticker: str (6位代码)
                - name: str (股票名称)
                - total_mv: float (总市值，万元)
                - circ_mv: float (流通市值，万元)
                - pe_ttm: float (市盈率 TTM)
                - pb: float (市净率)
                - list_date: str (上市日期 YYYYMMDD)
                - industry_lv1: str (行业分类，暂时为 None)
                - industry_lv2: str (行业分类，暂时为 None)
                - industry_lv3: str (行业分类，暂时为 None)
                - concepts: list (概念板块，暂时为空列表)
                - last_sync: datetime (同步时间)
        """
        # 标准化股票代码
        tickers = TickerNormalizer.normalize_batch(list(tickers))
        if not tickers:
            return pd.DataFrame()

        LOGGER.info("获取元数据 | tickers=%s", tickers)

        # 获取最新交易日
        latest_date = self.client.get_latest_trade_date()
        LOGGER.debug("使用交易日期: %s", latest_date)

        # OPTIMIZATION: Preload basic stock list once instead of in loop
        LOGGER.debug("预加载股票基本信息...")
        basic_df = self.client.fetch_stock_list()
        LOGGER.debug("✓ 已加载 %d 只股票的基本信息", len(basic_df))

        # OPTIMIZATION: Convert to dict for O(1) lookup instead of filtering DataFrame
        basic_dict = basic_df.set_index('ts_code').to_dict('index')
        LOGGER.debug("✓ 已索引基本信息字典")

        # OPTIMIZATION: Batch fetch daily_basic for entire trade date (1 API call vs 5000)
        LOGGER.debug("批量获取每日指标 | trade_date=%s", latest_date)
        daily_basic_df = self.client.fetch_daily_basic(trade_date=latest_date)
        daily_basic_dict = daily_basic_df.set_index('ts_code').to_dict('index')
        LOGGER.debug("✓ 已加载 %d 只股票的每日指标", len(daily_basic_df))

        records: List[dict] = []

        for ticker in tickers:
            try:
                ts_code = self.client.normalize_ts_code(ticker)

                # Use preloaded dicts for O(1) lookup
                stock_info = basic_dict.get(ts_code, {})

                # Get daily_basic data from preloaded dict
                daily_basic_row = daily_basic_dict.get(ts_code, {})

                # 构建元数据记录
                record = {
                    'ticker': ticker,
                    'name': stock_info.get('name', ''),
                    'total_mv': None,
                    'circ_mv': None,
                    'pe_ttm': None,
                    'pb': None,
                    'list_date': None,
                    'industry_lv1': None,
                    'industry_lv2': None,
                    'industry_lv3': None,
                    'concepts': [],  # 概念从 board_mapping 表获取
                    'last_sync': datetime.now(timezone.utc)
                }

                # 填充基本信息 (from dict, not DataFrame)
                if 'list_date' in stock_info:
                    list_date_val = stock_info['list_date']
                    if pd.notna(list_date_val):
                        record['list_date'] = str(list_date_val)

                # 注意: 不再从 stock_basic.industry 写入 industry_lv1
                # industry_lv1 现在只由 update_industry_daily.py 从同花顺成分股关系写入

                # 填充估值指标 (from preloaded dict)
                for field in ['total_mv', 'circ_mv', 'pe_ttm', 'pb']:
                    if field in daily_basic_row:
                        val = daily_basic_row[field]
                        if pd.notna(val):
                            record[field] = float(val)

                records.append(record)

                LOGGER.debug(
                    "获取元数据成功: %s | name=%s, total_mv=%.2f万, pe_ttm=%.2f",
                    ticker,
                    record['name'],
                    record['total_mv'] or 0,
                    record['pe_ttm'] or 0
                )

            except Exception as e:
                LOGGER.warning("获取 %s 元数据失败: %s", ticker, e)
                # 添加空记录
                records.append({
                    'ticker': ticker,
                    'name': ticker,
                    'total_mv': None,
                    'circ_mv': None,
                    'pe_ttm': None,
                    'pb': None,
                    'list_date': None,
                    'industry_lv1': None,
                    'industry_lv2': None,
                    'industry_lv3': None,
                    'concepts': [],
                    'last_sync': datetime.now(timezone.utc)
                })

        return pd.DataFrame(records)

    def fetch_all_tickers(self) -> List[str]:
        """
        获取所有上市股票代码

        Returns:
            List[str]: 6位股票代码列表
        """
        LOGGER.info("获取所有股票列表")

        df = self.client.fetch_stock_list(list_status='L')

        # 转换为6位代码
        tickers = [
            self.client.denormalize_ts_code(ts_code)
            for ts_code in df['ts_code'].tolist()
        ]

        # 标准化
        tickers = TickerNormalizer.normalize_batch(tickers)

        LOGGER.info("获取到 %d 只股票", len(tickers))

        return tickers

    def fetch_latest_prices(self, tickers: List[str]) -> dict[str, float]:
        """
        获取最新价格

        Args:
            tickers: 股票代码列表

        Returns:
            dict: {ticker: close_price}
        """
        tickers = TickerNormalizer.normalize_batch(tickers)
        if not tickers:
            return {}

        LOGGER.info("获取最新价格 | count=%d", len(tickers))

        latest_date = self.client.get_latest_trade_date()

        prices = {}

        for ticker in tickers:
            try:
                ts_code = self.client.normalize_ts_code(ticker)
                df = self.client.fetch_daily(ts_code=ts_code, trade_date=latest_date)

                if not df.empty and 'close' in df.columns:
                    prices[ticker] = float(df['close'].iloc[0])

            except Exception as e:
                LOGGER.warning("获取 %s 价格失败: %s", ticker, e)

        return prices
