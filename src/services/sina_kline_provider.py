"""
新浪财经K线数据提供者
用于获取分钟级K线数据
"""
import time
import requests
from typing import List, Optional
from datetime import datetime
import pandas as pd

from src.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Rate-limit status codes that trigger backoff
RATE_LIMIT_CODES = {429, 456}


class RateLimitError(Exception):
    """Raised when the provider is rate-limited and aborts a batch."""
    pass


class SinaKlineProvider:
    """新浪财经K线数据提供者"""

    BASE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

    # 周期映射
    PERIOD_MAP = {
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "60m": 60,
        "day": 240,
    }

    def __init__(
        self,
        delay: float = 3.0,
        max_consecutive_failures: int = 5,
        backoff_base: float = 5.0,
        backoff_max: float = 60.0,
    ):
        """
        初始化

        Args:
            delay: 请求间隔（秒），默认3秒（保守策略）
            max_consecutive_failures: 连续失败多少次后中止批量请求
            backoff_base: 指数退避基础秒数
            backoff_max: 指数退避最大秒数
        """
        self.delay = delay
        self.max_consecutive_failures = max_consecutive_failures
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.sina.com.cn/'
        })
        self._last_request_time = 0
        self._consecutive_failures = 0
        self._rate_limited = False
        LOGGER.info(
            f"SinaKlineProvider 初始化，请求间隔: {delay}秒, "
            f"最大连续失败: {max_consecutive_failures}"
        )

    @property
    def consecutive_failures(self) -> int:
        """Current consecutive failure count (read-only)."""
        return self._consecutive_failures

    @property
    def rate_limited(self) -> bool:
        """Whether the provider is currently in rate-limited state."""
        return self._rate_limited

    def reset(self):
        """Reset failure / rate-limit state (e.g. for a new batch)."""
        self._consecutive_failures = 0
        self._rate_limited = False

    def _wait_for_rate_limit(self):
        """等待以满足频率限制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            sleep_time = self.delay - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _backoff_sleep(self):
        """Exponential backoff based on consecutive failure count."""
        exponent = max(0, self._consecutive_failures - 1)
        sleep_secs = min(self.backoff_base * (2 ** exponent), self.backoff_max)
        LOGGER.warning(
            f"Rate-limited — backing off {sleep_secs:.1f}s "
            f"(consecutive failures: {self._consecutive_failures})"
        )
        time.sleep(sleep_secs)

    def _convert_ticker(self, ticker: str) -> str:
        """
        转换股票代码为新浪格式

        Args:
            ticker: 6位股票代码 (如 000001)

        Returns:
            新浪格式代码 (如 sz000001)
        """
        if ticker.startswith('6'):
            return f'sh{ticker}'
        elif ticker.startswith('0') or ticker.startswith('3'):
            return f'sz{ticker}'
        else:
            return ticker

    def fetch_kline(
        self,
        ticker: str,
        period: str = "30m",
        limit: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        获取单只股票的K线数据

        Args:
            ticker: 6位股票代码
            period: 周期 (5m, 15m, 30m, 60m)
            limit: 获取数量，最大1023

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        if period not in self.PERIOD_MAP:
            LOGGER.error(f"不支持的周期: {period}")
            return None

        scale = self.PERIOD_MAP[period]
        symbol = self._convert_ticker(ticker)

        self._wait_for_rate_limit()

        try:
            params = {
                'symbol': symbol,
                'scale': scale,
                'ma': 'no',
                'datalen': min(limit, 1023)
            }

            response = self.session.get(self.BASE_URL, params=params, timeout=10)

            # --- rate-limit detection ---
            if response.status_code in RATE_LIMIT_CODES:
                self._consecutive_failures += 1
                self._rate_limited = True
                LOGGER.warning(
                    f"{ticker} 被限流 (HTTP {response.status_code})，"
                    f"连续失败: {self._consecutive_failures}"
                )
                self._backoff_sleep()
                return None

            response.raise_for_status()

            # Success — reset streak
            self._consecutive_failures = 0
            self._rate_limited = False

            # 解析JSON响应
            data = response.json()

            if not data:
                LOGGER.debug(f"{ticker} 无数据返回")
                return None

            # 转换为DataFrame
            df = pd.DataFrame(data)

            # 重命名列
            df = df.rename(columns={
                'day': 'timestamp',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume'
            })

            # 转换数据类型
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            for col in ['open', 'high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype(int)

            # 添加ticker列
            df['ticker'] = ticker

            LOGGER.debug(f"{ticker} 获取 {len(df)} 条K线")
            return df

        except requests.exceptions.RequestException as e:
            self._consecutive_failures += 1
            LOGGER.warning(
                f"{ticker} 请求失败: {e} "
                f"(连续失败: {self._consecutive_failures})"
            )
            return None
        except Exception as e:
            self._consecutive_failures += 1
            LOGGER.warning(
                f"{ticker} 解析失败: {e} "
                f"(连续失败: {self._consecutive_failures})"
            )
            return None

    def fetch_batch(
        self,
        tickers: List[str],
        period: str = "30m",
        limit: int = 500,
        progress_callback=None
    ) -> pd.DataFrame:
        """
        批量获取多只股票的K线数据

        Aborts early when *max_consecutive_failures* successive requests fail
        (e.g. due to 456 rate-limiting), to avoid blocking for minutes.

        Args:
            tickers: 股票代码列表
            period: 周期
            limit: 每只股票获取数量
            progress_callback: 进度回调函数 (current, total, ticker)

        Returns:
            合并后的DataFrame
        """
        all_data = []
        total = len(tickers)

        # Reset state for a fresh batch
        self.reset()

        LOGGER.info(f"开始批量获取 {total} 只股票的 {period} K线")

        for i, ticker in enumerate(tickers):
            # --- circuit breaker ---
            if self._consecutive_failures >= self.max_consecutive_failures:
                LOGGER.warning(
                    f"连续 {self._consecutive_failures} 次请求失败，"
                    f"中止批量获取 (已完成 {i}/{total})"
                )
                break

            df = self.fetch_kline(ticker, period, limit)
            if df is not None and not df.empty:
                all_data.append(df)

            if progress_callback:
                progress_callback(i + 1, total, ticker)

            if (i + 1) % 100 == 0:
                LOGGER.info(f"进度: {i + 1}/{total} ({(i+1)/total*100:.1f}%)")

        if all_data:
            result = pd.concat(all_data, ignore_index=True)
            LOGGER.info(f"批量获取完成，共 {len(result)} 条K线")
            return result
        else:
            return pd.DataFrame()
