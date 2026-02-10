"""
同花顺板块数据服务
数据来源: TuShare Pro 同花顺接口
替代原来的东方财富(AKShare)数据源
"""

from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from src.config import get_settings
from src.services.tushare_client import TushareClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

# ── 热门概念关键词（用于从同花顺概念索引中筛选自选热门） ──
# 映射: watchlist category -> 同花顺概念/行业名称列表
CATEGORY_TO_THS_CONCEPTS: Dict[str, List[str]] = {
    "半导体": ["半导体", "芯片", "先进封装", "存储芯片", "光刻机", "第三代半导体", "国家大基金持股", "汽车芯片", "MCU芯片", "中芯国际概念"],
    "芯片": ["芯片", "半导体", "国产芯片"],
    "AI应用": ["人工智能", "AI应用", "ChatGPT概念", "算力", "AI芯片"],
    "机器人": ["人形机器人", "机器人概念", "机器人"],
    "光伏": ["光伏设备", "光伏", "太阳能"],
    "新能源汽车": ["新能源汽车", "锂电池", "充电桩"],
    "军工": ["军工", "国防军工"],
    "创新药": ["创新药", "CXO", "生物医药"],
    "PCB": ["PCB", "印制电路板"],
    "可控核聚变": ["可控核聚变", "核电"],
    "脑机接口": ["脑机接口"],
    "贵金属": ["黄金概念", "贵金属"],
    "金属": ["有色金属", "小金属", "稀土永磁"],
    "消费": ["食品饮料", "白酒概念"],
    "发电": ["电力", "特高压", "电网设备"],
}


def _create_client() -> TushareClient:
    """Create a TushareClient instance from settings."""
    settings = get_settings()
    return TushareClient(
        token=settings.tushare_token,
        points=settings.tushare_points,
    )


class TonghuashunService:
    """同花顺板块数据服务 — 通过 TuShare Pro 获取同花顺行业/概念数据。"""

    def __init__(self, client: Optional[TushareClient] = None):
        self._client = client

    @property
    def client(self) -> TushareClient:
        if self._client is None:
            self._client = _create_client()
        return self._client

    # ───────── 行业涨跌排名 ─────────

    def get_industry_ranking(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取同花顺一级行业涨跌幅排名。

        Returns DataFrame with columns:
            ts_code, name, pct_change, net_amount, company_num,
            close, lead_stock, pct_change_stock, close_price,
            net_buy_amount, net_sell_amount
        sorted by pct_change descending.
        """
        if trade_date is None:
            trade_date = self.client.get_latest_trade_date()

        df = self.client.fetch_ths_industry_moneyflow(trade_date=trade_date)

        if df.empty:
            logger.warning("fetch_ths_industry_moneyflow returned empty DataFrame")
            return pd.DataFrame()

        # Sort by pct_change descending
        df = df.sort_values("pct_change", ascending=False).reset_index(drop=True)
        return df

    # ───────── 概念涨跌排名 ─────────

    def get_concept_ranking(self) -> pd.DataFrame:
        """
        获取同花顺概念指数列表。

        Returns DataFrame columns: ts_code, name, count, exchange, list_date, type
        Note: 概念指数本身不含涨跌幅，需结合其他接口（如日K线）计算。
        """
        df = self.client.fetch_ths_index(exchange="A", type="N")
        if df.empty:
            logger.warning("fetch_ths_index(type=N) returned empty")
        return df

    # ───────── 板块成分股 ─────────

    def get_board_stocks(self, ts_code: str) -> pd.DataFrame:
        """
        获取板块成分股列表。

        Args:
            ts_code: 板块指数代码 (e.g. '883300.TI')

        Returns DataFrame columns: ts_code, code, name, weight, in_date, is_new
        """
        df = self.client.fetch_ths_member(ts_code=ts_code)
        if df.empty:
            logger.warning(f"fetch_ths_member({ts_code}) returned empty")
        return df

    # ───────── 自选概念映射 ─────────

    def get_watch_concept_names(self, categories: Optional[List[str]] = None) -> List[str]:
        """
        根据 watchlist categories 返回对应的同花顺概念名称列表。
        如果未提供 categories，返回所有映射过的概念名称。
        """
        if categories is None:
            # Return all mapped concept names
            all_names: List[str] = []
            for names in CATEGORY_TO_THS_CONCEPTS.values():
                all_names.extend(names)
            return list(dict.fromkeys(all_names))  # dedupe preserving order

        result: List[str] = []
        for cat in categories:
            result.extend(CATEGORY_TO_THS_CONCEPTS.get(cat, []))
        return list(dict.fromkeys(result))


# Module-level singleton
tonghuashun_service = TonghuashunService()
