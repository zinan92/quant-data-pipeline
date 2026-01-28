"""
美股服务
整合 Yahoo Finance 数据，提供美股行情、K线、中概股监控
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd

from src.services.yahoo_finance_provider import YahooFinanceProvider

logger = logging.getLogger(__name__)


class USStockService:
    """美股服务"""
    
    # 监控列表
    WATCHLISTS = {
        'indexes': {
            '^GSPC': 'S&P 500',
            '^DJI': '道琼斯',
            '^IXIC': '纳斯达克',
            '^NDX': '纳斯达克100',
            '^VIX': '恐慌指数',
        },
        'tech': {
            'AAPL': '苹果',
            'MSFT': '微软', 
            'GOOGL': '谷歌',
            'AMZN': '亚马逊',
            'NVDA': '英伟达',
            'META': 'Meta',
            'TSLA': '特斯拉',
            'AMD': 'AMD',
        },
        'china_adr': {
            'BABA': '阿里巴巴',
            'PDD': '拼多多',
            'JD': '京东',
            'BIDU': '百度',
            'NIO': '蔚来',
            'XPEV': '小鹏',
            'LI': '理想',
            'BILI': 'B站',
            'FUTU': '富途',
        },
        'ai': {
            'NVDA': '英伟达',
            'AMD': 'AMD',
            'MSFT': '微软',
            'GOOGL': '谷歌',
            'META': 'Meta',
            'PLTR': 'Palantir',
            'AI': 'C3.ai',
            'PATH': 'UiPath',
        },
    }
    
    def __init__(self):
        self.provider = YahooFinanceProvider()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 60  # 缓存60秒
        logger.info("US Stock Service initialized")
    
    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache:
            return False
        cached = self._cache[key]
        elapsed = (datetime.now() - cached['timestamp']).total_seconds()
        return elapsed < self._cache_ttl
    
    def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取单个股票实时报价
        
        Args:
            symbol: 股票代码 (如 AAPL, ^GSPC)
        """
        cache_key = f"quote_{symbol}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]['data']
        
        quote = self.provider.get_quote(symbol)
        if quote:
            self._cache[cache_key] = {
                'data': quote,
                'timestamp': datetime.now()
            }
        return quote
    
    def get_watchlist_quotes(self, watchlist: str = 'indexes') -> List[Dict[str, Any]]:
        """
        获取监控列表报价
        
        Args:
            watchlist: 监控列表名 (indexes/tech/china_adr/ai)
        """
        if watchlist not in self.WATCHLISTS:
            logger.warning(f"Unknown watchlist: {watchlist}")
            return []
        
        symbols = list(self.WATCHLISTS[watchlist].keys())
        quotes = []
        
        for symbol in symbols:
            quote = self.get_quote(symbol)
            if quote:
                # 添加中文名称
                quote['cn_name'] = self.WATCHLISTS[watchlist].get(symbol, '')
                quotes.append(quote)
        
        return quotes
    
    def get_indexes(self) -> List[Dict[str, Any]]:
        """获取美股主要指数"""
        return self.get_watchlist_quotes('indexes')
    
    def get_china_adr(self) -> List[Dict[str, Any]]:
        """获取中概股"""
        return self.get_watchlist_quotes('china_adr')
    
    def get_tech_stocks(self) -> List[Dict[str, Any]]:
        """获取科技股"""
        return self.get_watchlist_quotes('tech')
    
    def get_ai_stocks(self) -> List[Dict[str, Any]]:
        """获取AI概念股"""
        return self.get_watchlist_quotes('ai')
    
    def get_kline(
        self,
        symbol: str,
        period: str = '1mo',
        interval: str = '1d'
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取K线数据
        
        Args:
            symbol: 股票代码
            period: 时间范围 (1d/5d/1mo/3mo/6mo/1y/2y/5y/max)
            interval: K线周期 (1m/5m/15m/30m/1h/1d/1wk/1mo)
        """
        df = self.provider.get_kline(symbol, period=period, interval=interval)
        if df is None or df.empty:
            return None
        
        # 转换为列表
        klines = []
        for _, row in df.iterrows():
            klines.append({
                'time': row.get('date', row.get('datetime', '')),
                'open': float(row.get('open', 0)),
                'high': float(row.get('high', 0)),
                'low': float(row.get('low', 0)),
                'close': float(row.get('close', 0)),
                'volume': int(row.get('volume', 0)),
            })
        
        return klines
    
    def get_market_summary(self) -> Dict[str, Any]:
        """
        获取美股市场概览
        """
        summary = {
            'timestamp': datetime.now().isoformat(),
            'indexes': [],
            'top_gainers': [],
            'top_losers': [],
            'china_adr_summary': {},
        }
        
        # 指数
        indexes = self.get_indexes()
        summary['indexes'] = indexes
        
        # 中概股摘要
        china_adr = self.get_china_adr()
        if china_adr:
            gainers = [s for s in china_adr if s.get('change_pct', 0) > 0]
            losers = [s for s in china_adr if s.get('change_pct', 0) < 0]
            summary['china_adr_summary'] = {
                'total': len(china_adr),
                'gainers': len(gainers),
                'losers': len(losers),
                'top_gainer': max(china_adr, key=lambda x: x.get('change_pct', 0)) if china_adr else None,
                'top_loser': min(china_adr, key=lambda x: x.get('change_pct', 0)) if china_adr else None,
            }
        
        return summary
    
    def get_available_watchlists(self) -> Dict[str, List[str]]:
        """获取可用的监控列表"""
        return {
            name: list(symbols.keys())
            for name, symbols in self.WATCHLISTS.items()
        }


# 单例
_us_stock_service: Optional[USStockService] = None

def get_us_stock_service() -> USStockService:
    """获取美股服务单例"""
    global _us_stock_service
    if _us_stock_service is None:
        _us_stock_service = USStockService()
    return _us_stock_service
