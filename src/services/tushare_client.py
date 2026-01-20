"""
Tushare Pro API Client
提供对 Tushare Pro 数据接口的封装，包含智能限流和重试机制
"""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd
import tushare as ts

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    智能限流器，根据积分等级控制 API 调用频率

    Tushare 限流规则：
    - < 2000积分：约 60次/分钟
    - 2000-5000积分：约 120次/分钟
    - 5000+积分：约 200次/分钟
    - 15000+积分：约 200-300次/分钟
    """

    def __init__(self, max_calls: int = 200, time_window: int = 60):
        """
        Args:
            max_calls: 时间窗口内的最大调用次数
            time_window: 时间窗口（秒）
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls: List[datetime] = []

    def wait_if_needed(self):
        """如果需要，等待直到可以发起新请求"""
        now = datetime.now()

        # 清理超出时间窗口的调用记录
        cutoff = now - timedelta(seconds=self.time_window)
        self.calls = [t for t in self.calls if t > cutoff]

        # 如果已达到限制，等待
        if len(self.calls) >= self.max_calls:
            oldest = self.calls[0]
            wait_time = (oldest + timedelta(seconds=self.time_window) - now).total_seconds()
            if wait_time > 0:
                logger.warning(
                    f"达到调用限制 ({self.max_calls}次/{self.time_window}秒)，"
                    f"等待 {wait_time:.1f} 秒"
                )
                time.sleep(wait_time + 0.1)  # 额外0.1秒缓冲

        # 记录本次调用
        self.calls.append(datetime.now())


class TushareClient:
    """
    Tushare Pro API 客户端

    功能：
    - 封装所有常用的 Tushare API
    - 自动限流（基于积分等级）
    - 自动重试（失败后等待1秒重试）
    - 数据格式标准化
    """

    def __init__(
        self,
        token: str,
        points: int = 15000,
        delay: float = 0.3,
        max_retries: int = 3
    ):
        """
        Args:
            token: Tushare Pro Token
            points: 积分等级（决定调用频率限制）
            delay: 每次请求后的基础延迟（秒）
            max_retries: 最大重试次数
        """
        if not token:
            raise ValueError("Tushare token 不能为空，请在 .env 文件中配置 TUSHARE_TOKEN")

        self.token = token
        self.points = points
        self.delay = delay
        self.max_retries = max_retries

        # 初始化 Tushare Pro API
        try:
            self.pro = ts.pro_api(token)
            logger.info(f"Tushare 客户端已初始化（积分：{points}）")
        except Exception as e:
            logger.error(f"Tushare 初始化失败: {e}")
            raise

        # 根据积分等级设置 Rate Limiter
        max_calls_per_minute = self._get_max_calls(points)
        self.rate_limiter = RateLimiter(max_calls=max_calls_per_minute, time_window=60)

        logger.info(f"限流设置：{max_calls_per_minute} 次/分钟，基础延迟 {delay} 秒")

    def _get_max_calls(self, points: int) -> int:
        """根据积分等级返回每分钟最大调用次数"""
        if points >= 15000:
            return 180  # 保守值，避免触发限流
        elif points >= 5000:
            return 150
        elif points >= 2000:
            return 100
        else:
            return 50

    def _request_with_retry(self, func, *args, **kwargs) -> pd.DataFrame:
        """
        带重试的请求包装器

        Args:
            func: Tushare API 函数
            *args, **kwargs: 函数参数

        Returns:
            DataFrame: API 返回的数据

        Raises:
            Exception: 重试max_retries次后仍失败
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                # 限流等待
                self.rate_limiter.wait_if_needed()

                # 调用 API
                df = func(*args, **kwargs)

                # 基础延迟
                time.sleep(self.delay)

                return df if df is not None else pd.DataFrame()

            except Exception as e:
                logger.warning(f"API 调用失败 (尝试 {attempt}/{self.max_retries}): {e}")

                if attempt == self.max_retries:
                    logger.error(f"API 调用失败，已达最大重试次数: {e}")
                    raise

                # 重试前等待1秒
                time.sleep(1)

        return pd.DataFrame()

    # ====================
    # 基础数据接口
    # ====================

    def fetch_stock_list(
        self,
        exchange: str = "",
        list_status: str = "L"
    ) -> pd.DataFrame:
        """
        获取股票列表

        Args:
            exchange: 交易所（SSE=上交所, SZSE=深交所, BSE=北交所，空=全部）
            list_status: 上市状态（L=上市, D=退市, P=暂停）

        Returns:
            DataFrame: 包含 ts_code, symbol, name, area, industry, list_date 等字段
        """
        logger.info(f"获取股票列表: exchange={exchange or '全部'}, status={list_status}")

        return self._request_with_retry(
            self.pro.stock_basic,
            exchange=exchange,
            list_status=list_status,
            fields='ts_code,symbol,name,area,industry,market,list_date'
        )

    # ====================
    # 行情数据接口
    # ====================

    def fetch_daily(
        self,
        ts_code: Optional[str] = None,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取日线行情数据

        Args:
            ts_code: 股票代码（如 000001.SZ）
            trade_date: 交易日期 YYYYMMDD
            start_date: 开始日期
            end_date: 结束日期

        注意：ts_code 和 trade_date 至少提供一个

        Returns:
            DataFrame: 包含 ts_code, trade_date, open, high, low, close, vol, amount 等字段
        """
        logger.debug(
            f"获取日线: ts_code={ts_code}, trade_date={trade_date}, "
            f"start={start_date}, end={end_date}"
        )

        return self._request_with_retry(
            self.pro.daily,
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date
        )

    def fetch_weekly(
        self,
        ts_code: Optional[str] = None,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取周线行情数据

        Args:
            ts_code: 股票代码
            trade_date: 交易日期（周五）
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame: 周K线数据
        """
        logger.debug(f"获取周线: ts_code={ts_code}")

        return self._request_with_retry(
            self.pro.weekly,
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date
        )

    def fetch_monthly(
        self,
        ts_code: Optional[str] = None,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取月线行情数据

        Args:
            ts_code: 股票代码
            trade_date: 交易日期（月末最后一个交易日）
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame: 月K线数据
        """
        logger.debug(f"获取月线: ts_code={ts_code}")

        return self._request_with_retry(
            self.pro.monthly,
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date
        )

    def fetch_mins(
        self,
        ts_code: str,
        freq: str = "30min",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 120
    ) -> pd.DataFrame:
        """
        获取分钟级行情数据（需要5000积分以上）

        Args:
            ts_code: 股票代码（如 000001.SZ）
            freq: 分钟周期（1min/5min/15min/30min/60min）
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            limit: 返回数据条数，默认120

        Returns:
            DataFrame: 包含 ts_code, trade_time, open, high, low, close, vol, amount 等字段
        """
        logger.debug(f"获取分钟线: ts_code={ts_code}, freq={freq}, limit={limit}")

        # 使用 stk_mins 接口获取分钟数据
        return self._request_with_retry(
            self.pro.stk_mins,
            ts_code=ts_code,
            freq=freq,
            start_date=start_date,
            end_date=end_date
        )

    # ====================
    # 每日指标接口（重要）
    # ====================

    def fetch_daily_basic(
        self,
        ts_code: Optional[str] = None,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取每日指标数据（PE、PB、市值等）

        Args:
            ts_code: 股票代码
            trade_date: 交易日期
            start_date: 开始日期
            end_date: 结束日期

        注意：推荐按 trade_date 查询（一次获取所有股票的指标）

        Returns:
            DataFrame: 包含 ts_code, trade_date, close, pe, pe_ttm, pb,
                      total_mv, circ_mv, turnover_rate 等字段
        """
        logger.debug(
            f"获取每日指标: ts_code={ts_code}, trade_date={trade_date}"
        )

        return self._request_with_retry(
            self.pro.daily_basic,
            ts_code=ts_code or "",
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            fields=(
                'ts_code,trade_date,close,turnover_rate,volume_ratio,'
                'pe,pe_ttm,pb,ps,ps_ttm,total_mv,circ_mv'
            )
        )

    # ====================
    # 公司信息接口
    # ====================

    def fetch_stock_company(
        self,
        ts_code: Optional[str] = None,
        exchange: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取上市公司基本信息

        Args:
            ts_code: 股票代码
            exchange: 交易所代码

        Returns:
            DataFrame: 包含公司名称、注册资本、所在地、主营业务等信息
        """
        logger.debug(f"获取公司信息: ts_code={ts_code}")

        return self._request_with_retry(
            self.pro.stock_company,
            ts_code=ts_code,
            exchange=exchange,
            fields='ts_code,chairman,manager,reg_capital,setup_date,province,city,website,employees,main_business'
        )

    # ====================
    # 板块数据接口
    # ====================

    def fetch_ths_index(
        self,
        ts_code: Optional[str] = None,
        exchange: str = "A",
        type: str = "N"
    ) -> pd.DataFrame:
        """
        获取同花顺板块指数列表

        Args:
            ts_code: 指数代码
            exchange: 市场类型（A=A股, HK=港股, US=美股）
            type: 指数类型
                  N=概念, I=行业, R=地域, S=特色,
                  ST=风格, TH=主题, BB=宽基

        Returns:
            DataFrame: 包含 ts_code, name, count, exchange, list_date, type 等字段
        """
        logger.info(f"获取同花顺板块: type={type}, exchange={exchange}")

        return self._request_with_retry(
            self.pro.ths_index,
            ts_code=ts_code,
            exchange=exchange,
            type=type
        )

    def fetch_ths_member(
        self,
        ts_code: Optional[str] = None,
        code: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取同花顺板块成分股

        Args:
            ts_code: 板块指数代码（如 885800.TI）
            code: 股票代码（用于反查该股票所属板块）

        Returns:
            DataFrame: 包含 ts_code, code, name, weight, in_date, is_new 等字段
        """
        logger.debug(f"获取板块成分: ts_code={ts_code}, code={code}")

        return self._request_with_retry(
            self.pro.ths_member,
            ts_code=ts_code,
            code=code
        )

    def fetch_ths_industry_moneyflow(
        self,
        trade_date: Optional[str] = None,
        ts_code: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取同花顺行业资金流向

        Args:
            trade_date: 交易日期 YYYYMMDD，默认为最新交易日
            ts_code: 行业代码（如 881267.TI），可选

        Returns:
            DataFrame: 包含 ts_code, trade_date, name, close, pct_change,
                      amount, net_amount, buy_elg_amount, sell_elg_amount 等字段
        """
        if trade_date is None:
            trade_date = self.get_latest_trade_date()

        logger.info(f"获取同花顺行业资金流向: trade_date={trade_date}")

        return self._request_with_retry(
            self.pro.moneyflow_ind_ths,
            trade_date=trade_date,
            ts_code=ts_code
        )

    def fetch_dc_index(
        self,
        ts_code: Optional[str] = None,
        name: Optional[str] = None,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取东方财富概念板块数据

        Args:
            ts_code: 指数代码（支持多个代码同时输入，用逗号分隔）
            name: 板块名称（例如：人形机器人）
            trade_date: 交易日期 YYYYMMDD
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD

        Returns:
            DataFrame: 包含 ts_code, trade_date, name, leading, leading_code,
                      pct_change, leading_pct, total_mv, turnover_rate, up_num, down_num 等字段
        """
        logger.info(f"获取东方财富概念板块: trade_date={trade_date}, name={name}")

        return self._request_with_retry(
            self.pro.dc_index,
            ts_code=ts_code,
            name=name,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date
        )

    # ====================
    # 辅助方法
    # ====================

    def get_latest_trade_date(self) -> str:
        """
        获取最新交易日期

        Returns:
            str: 日期字符串 YYYYMMDD
        """
        today = datetime.now().strftime('%Y%m%d')

        try:
            # 获取交易日历
            df = self._request_with_retry(
                self.pro.trade_cal,
                exchange='SSE',
                start_date=(datetime.now() - timedelta(days=10)).strftime('%Y%m%d'),
                end_date=today
            )

            # 过滤出交易日
            trade_days = df[df['is_open'] == 1]['cal_date'].tolist()

            if trade_days:
                # Tushare 返回的是降序排列，取第一个元素（最新日期）
                return trade_days[0]  # 最新的交易日

        except Exception as e:
            logger.warning(f"获取交易日历失败: {e}")

        # 降级方案：返回今天
        return today

    def normalize_ts_code(self, ticker: str) -> str:
        """
        标准化股票代码为 Tushare 格式

        Args:
            ticker: 6位股票代码（如 000001 或 600000）

        Returns:
            str: Tushare 格式代码（如 000001.SZ 或 600000.SH）
        """
        if '.' in ticker:
            return ticker

        # 6开头为上交所，其他为深交所
        if ticker.startswith('6'):
            return f"{ticker}.SH"
        elif ticker.startswith('4') or ticker.startswith('8'):
            return f"{ticker}.BJ"  # 北交所
        else:
            return f"{ticker}.SZ"

    def denormalize_ts_code(self, ts_code: str) -> str:
        """
        去掉 Tushare 代码后缀，返回6位代码

        Args:
            ts_code: Tushare 格式代码（如 000001.SZ）

        Returns:
            str: 6位股票代码（如 000001）
        """
        return ts_code.split('.')[0]

    # ====================
    # 指数数据接口
    # ====================

    def fetch_index_daily(
        self,
        ts_code: str = "000001.SH",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取指数日线行情数据

        Args:
            ts_code: 指数代码（如 000001.SH=上证指数, 399001.SZ=深证成指）
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD

        Returns:
            DataFrame: 包含 ts_code, trade_date, open, high, low, close, vol, amount 等字段
        """
        logger.debug(f"获取指数日线: ts_code={ts_code}, start={start_date}, end={end_date}")

        return self._request_with_retry(
            self.pro.index_daily,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date
        )

    def fetch_index_dailybasic(
        self,
        ts_code: str = "000001.SH",
        trade_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取指数每日指标数据（市盈率、市净率、成交量等）

        Args:
            ts_code: 指数代码
            trade_date: 交易日期 YYYYMMDD

        Returns:
            DataFrame: 包含 pe, pe_ttm, pb, total_mv, float_mv, turnover_rate 等字段
        """
        logger.debug(f"获取指数指标: ts_code={ts_code}, trade_date={trade_date}")

        return self._request_with_retry(
            self.pro.index_dailybasic,
            ts_code=ts_code,
            trade_date=trade_date,
            fields='ts_code,trade_date,total_mv,float_mv,total_share,float_share,free_share,turnover_rate,turnover_rate_f,pe,pe_ttm,pb'
        )
