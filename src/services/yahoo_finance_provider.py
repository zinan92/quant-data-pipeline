"""
Yahoo Finance 数据提供器
获取美股实时行情和 K 线数据
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from src.utils.logging import get_logger

logger = get_logger(__name__)


class YahooFinanceProvider:
    """Yahoo Finance 数据提供器"""

    # 常用美股指数
    US_INDEXES = {
        "^GSPC": "S&P 500",
        "^DJI": "道琼斯工业",
        "^IXIC": "纳斯达克综合",
        "^NDX": "纳斯达克100",
        "^VIX": "恐慌指数",
        "^RUT": "罗素2000",
    }

    # 热门美股
    POPULAR_STOCKS = {
        "AAPL": "苹果",
        "MSFT": "微软",
        "GOOGL": "谷歌",
        "AMZN": "亚马逊",
        "NVDA": "英伟达",
        "META": "Meta",
        "TSLA": "特斯拉",
        "AMD": "AMD",
        "INTC": "英特尔",
        "NFLX": "奈飞",
    }

    # 中概股
    CHINA_ADRS = {
        "BABA": "阿里巴巴",
        "PDD": "拼多多",
        "JD": "京东",
        "BIDU": "百度",
        "NIO": "蔚来",
        "XPEV": "小鹏汽车",
        "LI": "理想汽车",
        "BILI": "哔哩哔哩",
        "TME": "腾讯音乐",
        "FUTU": "富途控股",
    }

    def __init__(self):
        logger.info("Yahoo Finance 提供器已初始化")

    def get_quote(self, symbol: str) -> Optional[Dict]:
        """
        获取实时报价

        Args:
            symbol: 股票代码 (如 AAPL, ^GSPC)

        Returns:
            {
                'symbol': 代码,
                'name': 名称,
                'price': 当前价,
                'change': 涨跌额,
                'change_pct': 涨跌幅,
                'volume': 成交量,
                'market_cap': 市值,
                'pe_ratio': 市盈率,
                'last_update': 更新时间
            }
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # 获取价格数据
            price = info.get('regularMarketPrice') or info.get('currentPrice', 0)
            prev_close = info.get('regularMarketPreviousClose', price)
            change = price - prev_close if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0

            return {
                'symbol': symbol,
                'name': info.get('shortName') or info.get('longName', symbol),
                'price': price,
                'change': round(change, 2),
                'change_pct': round(change_pct, 2),
                'volume': info.get('regularMarketVolume', 0),
                'market_cap': info.get('marketCap', 0),
                'pe_ratio': info.get('trailingPE', 0),
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        except Exception as e:
            logger.error(f"获取 {symbol} 报价失败: {e}")
            return None

    def get_quotes_batch(self, symbols: List[str]) -> List[Dict]:
        """
        批量获取实时报价

        Args:
            symbols: 股票代码列表

        Returns:
            报价列表
        """
        results = []
        for symbol in symbols:
            quote = self.get_quote(symbol)
            if quote:
                results.append(quote)
        return results

    def get_kline(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """
        获取 K 线数据

        Args:
            symbol: 股票代码
            period: 时间范围 (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: K 线周期 (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)

        Returns:
            DataFrame with columns: datetime, open, high, low, close, volume
        """
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)

            if df.empty:
                logger.warning(f"{symbol} 无 K 线数据")
                return None

            # 重命名列
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]

            # 标准化列名
            if 'date' in df.columns:
                df = df.rename(columns={'date': 'datetime'})
            elif 'datetime' not in df.columns and df.index.name:
                df = df.reset_index()
                df = df.rename(columns={df.columns[0]: 'datetime'})

            # 选择需要的列
            cols = ['datetime', 'open', 'high', 'low', 'close', 'volume']
            available_cols = [c for c in cols if c in df.columns]
            df = df[available_cols]

            return df

        except Exception as e:
            logger.error(f"获取 {symbol} K 线失败: {e}")
            return None

    def get_us_index_summary(self) -> List[Dict]:
        """获取美股主要指数摘要"""
        return self.get_quotes_batch(list(self.US_INDEXES.keys()))

    def get_china_adr_summary(self) -> List[Dict]:
        """获取中概股摘要"""
        return self.get_quotes_batch(list(self.CHINA_ADRS.keys()))

    def get_market_status(self) -> Dict:
        """
        获取美股市场状态

        Returns:
            {
                'is_open': 是否开盘,
                'status': 状态描述,
                'next_open': 下次开盘时间,
                'next_close': 下次收盘时间
            }
        """
        try:
            # 使用 SPY ETF 获取市场状态
            spy = yf.Ticker("SPY")
            info = spy.info

            # 检查市场状态
            market_state = info.get('marketState', 'UNKNOWN')

            status_map = {
                'REGULAR': ('开盘中', True),
                'PRE': ('盘前交易', True),
                'POST': ('盘后交易', True),
                'CLOSED': ('已收盘', False),
                'PREPRE': ('盘前准备', False),
                'POSTPOST': ('盘后结束', False),
            }

            status, is_open = status_map.get(market_state, ('未知', False))

            return {
                'is_open': is_open,
                'status': status,
                'market_state': market_state,
                'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        except Exception as e:
            logger.error(f"获取市场状态失败: {e}")
            return {
                'is_open': False,
                'status': '获取失败',
                'market_state': 'ERROR',
                'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }


def get_us_market_briefing() -> str:
    """
    生成美股市场简报

    Returns:
        格式化的市场简报文本
    """
    provider = YahooFinanceProvider()

    lines = []
    lines.append("## 🇺🇸 美股市场\n")

    # 市场状态
    status = provider.get_market_status()
    lines.append(f"**状态**: {status['status']}\n")

    # 主要指数
    lines.append("### 📊 主要指数\n")
    indexes = provider.get_us_index_summary()
    for idx in indexes:
        emoji = "🟢" if idx['change_pct'] >= 0 else "🔴"
        lines.append(
            f"{emoji} **{idx['name']}**: {idx['price']:,.2f} "
            f"({idx['change_pct']:+.2f}%)"
        )

    # 中概股
    lines.append("\n### 🐉 中概股\n")
    adrs = provider.get_china_adr_summary()
    for stock in adrs[:5]:  # 只显示前5个
        emoji = "🟢" if stock['change_pct'] >= 0 else "🔴"
        lines.append(
            f"{emoji} **{stock['name']}** ({stock['symbol']}): "
            f"${stock['price']:.2f} ({stock['change_pct']:+.2f}%)"
        )

    return "\n".join(lines)
