"""
东方财富K线数据提供者
用于获取分钟级K线数据
"""
import time
import logging
import requests
from typing import List, Optional
from datetime import datetime
import pandas as pd

LOGGER = logging.getLogger(__name__)


class EastMoneyKlineProvider:
    """东方财富K线数据提供者"""

    # 周期映射 (东方财富的klt参数)
    PERIOD_MAP = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "60m": 60,
        "day": 101,
        "week": 102,
        "month": 103,
    }

    def __init__(self, delay: float = 0.1):
        """
        初始化

        Args:
            delay: 请求间隔（秒），默认0.1秒
        """
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/'
        })
        self._last_request_time = 0
        LOGGER.info(f"EastMoneyKlineProvider 初始化，请求间隔: {delay}秒")

    def _wait_for_rate_limit(self):
        """等待以满足频率限制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            sleep_time = self.delay - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _convert_ticker(self, ticker: str) -> str:
        """
        转换股票代码为东方财富格式

        Args:
            ticker: 6位股票代码 (如 000001)

        Returns:
            东方财富格式: 1.000001 (深圳) 或 0.600000 (上海)
        """
        if ticker.startswith('6'):
            return f'1.{ticker}'  # 上海
        elif ticker.startswith('0') or ticker.startswith('3'):
            return f'0.{ticker}'  # 深圳
        else:
            return f'0.{ticker}'

    def _get_secid(self, ticker: str) -> str:
        """获取东方财富的secid"""
        if ticker.startswith('6'):
            return f'1.{ticker}'
        else:
            return f'0.{ticker}'

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
            period: 周期 (1m, 5m, 15m, 30m, 60m, day, week, month)
            limit: 获取数量

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        if period not in self.PERIOD_MAP:
            LOGGER.error(f"不支持的周期: {period}")
            return None

        klt = self.PERIOD_MAP[period]
        secid = self._get_secid(ticker)

        self._wait_for_rate_limit()

        try:
            url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            params = {
                'secid': secid,
                'fields1': 'f1,f2,f3,f4,f5,f6',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57',
                'klt': klt,
                'fqt': 1,  # 前复权
                'end': '20500101',
                'lmt': limit,
            }

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get('data') is None or data['data'].get('klines') is None:
                LOGGER.debug(f"{ticker} 无数据返回")
                return None

            klines = data['data']['klines']

            if not klines:
                return None

            # 解析K线数据
            # 格式: "2024-01-02 10:00,10.50,10.80,10.30,10.60,123456,1234567.00"
            records = []
            for line in klines:
                parts = line.split(',')
                if len(parts) >= 6:
                    records.append({
                        'timestamp': parts[0],
                        'open': float(parts[1]),
                        'close': float(parts[2]),
                        'high': float(parts[3]),
                        'low': float(parts[4]),
                        'volume': int(float(parts[5])),
                    })

            df = pd.DataFrame(records)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['ticker'] = ticker

            LOGGER.debug(f"{ticker} 获取 {len(df)} 条K线")
            return df

        except requests.exceptions.RequestException as e:
            LOGGER.warning(f"{ticker} 请求失败: {e}")
            return None
        except Exception as e:
            LOGGER.warning(f"{ticker} 解析失败: {e}")
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

        LOGGER.info(f"开始批量获取 {total} 只股票的 {period} K线 (东方财富)")

        for i, ticker in enumerate(tickers):
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
