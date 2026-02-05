"""
美股服务
整合 Yahoo Finance 数据，提供美股行情、K线、板块、商品、债券监控
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd

from src.services.yahoo_finance_provider import YahooFinanceProvider

logger = logging.getLogger(__name__)


class USStockService:
    """美股服务"""

    # ── 板块 + Mag7 监控列表 ──
    # 包含 A股对标板块 + 美股特有板块
    WATCHLISTS = {
        # ── 核心指数 ──
        'indexes': {
            '^GSPC': 'S&P 500', '^DJI': '道琼斯', '^IXIC': '纳斯达克',
            '^NDX': '纳斯达克100', '^VIX': '恐慌指数',
        },
        'mag7': {
            'AAPL': '苹果', 'MSFT': '微软', 'GOOGL': '谷歌', 'AMZN': '亚马逊',
            'NVDA': '英伟达', 'META': 'Meta', 'TSLA': '特斯拉',
        },
        # ── A股对标板块 (21个) ──
        'semiconductors': {
            'NVDA': '英伟达', 'AMD': 'AMD', 'AVGO': '博通', 'QCOM': '高通',
            'TSM': '台积电', 'ASML': 'ASML', 'INTC': '英特尔',
        },
        'ai_application': {
            'PLTR': 'Palantir', 'AI': 'C3.ai', 'PATH': 'UiPath',
            'SNOW': 'Snowflake', 'CRM': 'Salesforce', 'NOW': 'ServiceNow',
        },
        'robotics': {
            'ISRG': 'Intuitive Surgical', 'ROK': 'Rockwell', 'TER': 'Teradyne',
            'AVAV': 'AeroVironment', 'IRBT': 'iRobot',
        },
        'defense': {
            'LMT': '洛克希德', 'RTX': '雷神', 'NOC': '诺格', 'GD': '通用动力',
            'LHX': 'L3Harris',
        },
        'lithium_battery': {
            'ALB': 'Albemarle', 'SQM': 'SQM', 'QS': 'QuantumScape',
            'ENVX': 'Enovix', 'ALTM': 'Arcadium Lithium',
        },
        'nuclear': {
            'CCJ': 'Cameco', 'NXE': 'NexGen', 'UEC': 'Uranium Energy',
            'CEG': 'Constellation', 'LEU': 'Centrus',
        },
        'utilities': {
            'NEE': 'NextEra', 'DUK': '杜克能源', 'SO': '南方电力',
        },
        'metals_mining': {
            'FCX': '自由港', 'CLF': 'Cleveland-Cliffs', 'NUE': 'Nucor',
            'STLD': 'Steel Dynamics', 'RIO': '力拓',
        },
        'biotech': {
            'AMGN': 'Amgen', 'GILD': 'Gilead', 'REGN': 'Regeneron',
            'MRNA': 'Moderna', 'BNTX': 'BioNTech',
        },
        'solar': {
            'ENPH': 'Enphase', 'FSLR': 'First Solar', 'ARRY': 'Array Tech',
            'RUN': 'Sunrun', 'NOVA': 'Sunnova',
        },
        'precious_metals': {
            'NEM': '纽蒙特', 'GOLD': 'Barrick', 'AEM': 'Agnico Eagle',
            'WPM': 'Wheaton', 'FNV': 'Franco-Nevada',
        },
        'financials': {
            'JPM': '摩根大通', 'BAC': '美银', 'GS': '高盛',
            'MS': '摩根士丹利', 'V': 'Visa',
        },
        'ai_infra': {
            'MSFT': '微软', 'CRM': 'Salesforce', 'NOW': 'ServiceNow',
            'PLTR': 'Palantir', 'SNOW': 'Snowflake',
        },
        'gaming_media': {
            'TTWO': 'Take-Two', 'EA': 'EA', 'RBLX': 'Roblox',
            'U': 'Unity', 'NFLX': '奈飞',
        },
        'travel': {
            'BKNG': 'Booking', 'MAR': '万豪', 'HLT': '希尔顿',
            'DAL': '达美航空', 'UAL': '美联航',
        },
        'genomics': {
            'TWST': 'Twist Bio', 'EXAS': 'Exact Sciences', 'NTRA': 'Natera',
            'RXRX': 'Recursion', 'CRSP': 'CRISPR',
        },
        'consumer_disc': {
            'AMZN': '亚马逊', 'TSLA': '特斯拉', 'HD': '家得宝',
            'MCD': '麦当劳', 'NKE': '耐克',
        },
        'consumer_staples': {
            'PG': '宝洁', 'KO': '可口可乐', 'WMT': '沃尔玛',
            'COST': 'Costco', 'PEP': '百事',
        },
        'space': {
            'RKLB': 'Rocket Lab', 'LHX': 'L3Harris', 'IRDM': 'Iridium',
            'LUNR': 'Intuitive Machines', 'SPCE': 'Virgin Galactic',
        },
        'cybersecurity': {
            'CRWD': 'CrowdStrike', 'PANW': 'Palo Alto', 'FTNT': 'Fortinet',
            'ZS': 'Zscaler', 'S': 'SentinelOne',
        },
        'quantum': {
            'IONQ': 'IonQ', 'RGTI': 'Rigetti', 'QBTS': 'D-Wave',
            'IBM': 'IBM', 'HON': 'Honeywell',
        },
        # ── 美股特有板块 ──
        'communication': {
            'META': 'Meta', 'GOOGL': '谷歌', 'NFLX': '奈飞',
            'DIS': '迪士尼', 'TMUS': 'T-Mobile',
        },
        'healthcare': {
            'UNH': '联合健康', 'LLY': '礼来', 'JNJ': '强生',
            'ABBV': '艾伯维', 'PFE': '辉瑞',
        },
        'energy': {
            'XOM': '埃克森美孚', 'CVX': '雪佛龙', 'COP': '康菲石油',
            'SLB': '斯伦贝谢',
        },
        'industrials': {
            'CAT': '卡特彼勒', 'BA': '波音', 'HON': '霍尼韦尔',
            'GE': 'GE', 'UPS': 'UPS',
        },
        'materials': {
            'LIN': '林德', 'APD': '空气化工', 'FCX': '自由港', 'NEM': '纽蒙特',
        },
        'real_estate': {
            'AMT': '美国电塔', 'PLD': '普洛斯', 'CCI': '冠城国际',
        },
        'ev_newenergy': {
            'TSLA': '特斯拉', 'NIO': '蔚来', 'XPEV': '小鹏',
            'LI': '理想', 'RIVN': 'Rivian', 'LCID': 'Lucid',
        },
        'crypto_fintech': {
            'COIN': 'Coinbase', 'SQ': 'Block', 'MARA': 'Marathon', 'RIOT': 'Riot',
        },
        'china_adr': {
            'BABA': '阿里巴巴', 'PDD': '拼多多', 'JD': '京东', 'BIDU': '百度',
            'NIO': '蔚来', 'XPEV': '小鹏', 'LI': '理想', 'BILI': 'B站', 'FUTU': '富途',
        },
    }

    # ── 板块 ETF 映射 ──
    SECTOR_ETFS = {
        # A股对标板块 (21个)
        'semiconductors': 'SMH', 'ai_application': 'AIQ', 'robotics': 'BOTZ',
        'defense': 'ITA', 'lithium_battery': 'LIT', 'nuclear': 'URA',
        'utilities': 'XLU', 'metals_mining': 'XME', 'biotech': 'XBI',
        'solar': 'TAN', 'precious_metals': 'GLD', 'financials': 'XLF',
        'ai_infra': 'IGV', 'gaming_media': 'HERO', 'travel': 'JETS',
        'genomics': 'ARKG', 'consumer_disc': 'XLY', 'consumer_staples': 'XLP',
        'space': 'ARKX', 'cybersecurity': 'CIBR', 'quantum': 'QTUM',
        # 美股通用板块
        'communication': 'XLC', 'healthcare': 'XLV',
        'energy': 'XLE', 'industrials': 'XLI', 'materials': 'XLB',
        'real_estate': 'XLRE', 'ev_newenergy': 'DRIV', 'crypto_fintech': 'BLOK',
    }

    # ── A股对标板块 key（用于跨市场对比）──
    ASHARE_MAPPED_SECTORS = [
        'ai_application', 'robotics', 'defense', 'lithium_battery', 'nuclear',
        'utilities', 'metals_mining', 'biotech', 'semiconductors', 'solar',
        'precious_metals', 'financials', 'ai_infra', 'gaming_media', 'travel',
        'genomics', 'consumer_disc', 'consumer_staples',
        'space', 'cybersecurity', 'quantum',
    ]

    # ── 板块中文名 ──
    SECTOR_NAMES = {
        'indexes': '主要指数', 'mag7': '科技七巨头',
        # A股对标板块
        'semiconductors': '半导体', 'ai_application': 'AI应用',
        'robotics': '机器人', 'defense': '军工',
        'lithium_battery': '储能锂电', 'nuclear': '可控核聚变',
        'utilities': '发电', 'metals_mining': '金属',
        'biotech': '创新药', 'solar': '光伏',
        'precious_metals': '贵金属', 'financials': '金融',
        'ai_infra': '算力/AI基建', 'gaming_media': '传媒游戏',
        'travel': '旅游', 'genomics': '基因科技',
        'consumer_disc': '可选消费', 'consumer_staples': '必需消费',
        'space': '太空探索', 'cybersecurity': '网络安全',
        'quantum': '量子计算',
        # 美股特有板块
        'communication': '通信服务', 'healthcare': '医疗健康',
        'energy': '能源', 'industrials': '工业', 'materials': '材料',
        'real_estate': '房地产', 'ev_newenergy': '电动车/新能源',
        'crypto_fintech': '加密/金融科技', 'china_adr': '中概股',
    }

    # ── 期货/商品 ──
    COMMODITIES = {
        'GC=F': '黄金', 'SI=F': '白银', 'CL=F': '原油WTI', 'BZ=F': '布伦特原油',
        'HG=F': '铜', 'NG=F': '天然气',
    }

    # ── 债券 ──
    BONDS = {
        '^TNX': '10Y美债', '^TYX': '30Y美债', '^FVX': '5Y美债',
    }

    # ── 外汇 ──
    FOREX = {
        'DX-Y.NYB': '美元指数',
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
        """获取单个股票实时报价"""
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
        """获取监控列表报价"""
        if watchlist not in self.WATCHLISTS:
            logger.warning(f"Unknown watchlist: {watchlist}")
            return []

        symbols = list(self.WATCHLISTS[watchlist].keys())
        quotes = []

        for symbol in symbols:
            quote = self.get_quote(symbol)
            if quote:
                quote['cn_name'] = self.WATCHLISTS[watchlist].get(symbol, '')
                quotes.append(quote)

        return quotes

    # ── 便捷板块方法 ──

    def get_indexes(self) -> List[Dict[str, Any]]:
        """获取美股主要指数"""
        return self.get_watchlist_quotes('indexes')

    def get_mag7(self) -> List[Dict[str, Any]]:
        """获取科技七巨头"""
        return self.get_watchlist_quotes('mag7')

    def get_china_adr(self) -> List[Dict[str, Any]]:
        """获取中概股"""
        return self.get_watchlist_quotes('china_adr')

    def get_tech_stocks(self) -> List[Dict[str, Any]]:
        """获取半导体板块 (原 tech)"""
        return self.get_watchlist_quotes('semiconductors')

    def get_ai_stocks(self) -> List[Dict[str, Any]]:
        """获取AI概念股"""
        return self.get_watchlist_quotes('ai_application')

    def get_sector(self, name: str) -> Dict[str, Any]:
        """获取单个板块详情（ETF + 个股）"""
        result: Dict[str, Any] = {
            'sector': name,
            'sector_cn': self.SECTOR_NAMES.get(name, name),
            'etf': None,
            'stocks': [],
        }

        # 板块ETF
        if name in self.SECTOR_ETFS:
            etf_symbol = self.SECTOR_ETFS[name]
            etf_quote = self.get_quote(etf_symbol)
            if etf_quote:
                result['etf'] = etf_quote

        # 板块个股
        if name in self.WATCHLISTS:
            result['stocks'] = self.get_watchlist_quotes(name)

        return result

    def get_all_sectors(self) -> List[Dict[str, Any]]:
        """获取所有板块概览"""
        # 跳过 indexes — 单独获取
        sector_keys = [k for k in self.WATCHLISTS if k != 'indexes']
        sectors = []
        for key in sector_keys:
            sector = {
                'name': key,
                'name_cn': self.SECTOR_NAMES.get(key, key),
                'etf': None,
                'stock_count': len(self.WATCHLISTS[key]),
            }
            # 板块ETF报价
            if key in self.SECTOR_ETFS:
                etf_symbol = self.SECTOR_ETFS[key]
                etf_quote = self.get_quote(etf_symbol)
                if etf_quote:
                    sector['etf'] = etf_quote
            sectors.append(sector)
        return sectors

    # ── 商品/债券/外汇 ──

    def _get_symbol_group(self, group: Dict[str, str]) -> List[Dict[str, Any]]:
        """通用方法：获取一组 symbol 的报价"""
        quotes = []
        for symbol, cn_name in group.items():
            quote = self.get_quote(symbol)
            if quote:
                quote['cn_name'] = cn_name
                quotes.append(quote)
        return quotes

    def get_commodities(self) -> List[Dict[str, Any]]:
        """获取期货/商品"""
        return self._get_symbol_group(self.COMMODITIES)

    def get_bonds(self) -> List[Dict[str, Any]]:
        """获取美债收益率"""
        return self._get_symbol_group(self.BONDS)

    def get_forex(self) -> List[Dict[str, Any]]:
        """获取外汇（美元指数）"""
        return self._get_symbol_group(self.FOREX)

    # ── K线 ──

    def get_kline(
        self,
        symbol: str,
        period: str = '1mo',
        interval: str = '1d'
    ) -> Optional[List[Dict[str, Any]]]:
        """获取K线数据"""
        df = self.provider.get_kline(symbol, period=period, interval=interval)
        if df is None or df.empty:
            return None

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

    # ── 市场概览 ──

    def get_market_summary(self) -> Dict[str, Any]:
        """获取美股市场概览（含板块、商品、债券）"""
        summary: Dict[str, Any] = {
            'timestamp': datetime.now().isoformat(),
            'indexes': [],
            'mag7': [],
            'sectors_overview': [],
            'commodities': [],
            'bonds': [],
            'forex': [],
            'china_adr_summary': {},
        }

        # 指数
        summary['indexes'] = self.get_indexes()

        # Mag7
        summary['mag7'] = self.get_mag7()

        # 板块概览（只拿ETF，不展开个股）
        for key in self.SECTOR_ETFS:
            etf_symbol = self.SECTOR_ETFS[key]
            etf_quote = self.get_quote(etf_symbol)
            if etf_quote:
                summary['sectors_overview'].append({
                    'sector': key,
                    'sector_cn': self.SECTOR_NAMES.get(key, key),
                    'etf': etf_quote,
                })

        # 商品/债券/外汇
        summary['commodities'] = self.get_commodities()
        summary['bonds'] = self.get_bonds()
        summary['forex'] = self.get_forex()

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
