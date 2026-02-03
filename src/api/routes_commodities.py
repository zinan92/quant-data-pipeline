"""
大宗商品实时数据API
使用 yfinance 获取黄金、白银、铜、原油期货实时价格及K线数据
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

# Commodity futures symbols on Yahoo Finance
COMMODITY_SYMBOLS = {
    "GC=F": {"name": "Gold", "name_cn": "黄金", "unit": "USD/oz"},
    "SI=F": {"name": "Silver", "name_cn": "白银", "unit": "USD/oz"},
    "HG=F": {"name": "Copper", "name_cn": "铜", "unit": "USD/lb"},
    "CL=F": {"name": "Crude Oil", "name_cn": "原油", "unit": "USD/bbl"},
}


class CommodityItem(BaseModel):
    symbol: str
    name: str
    name_cn: str
    unit: str
    price: float
    change: float
    change_pct: float
    high_24h: float
    low_24h: float
    open_price: float
    prev_close: float
    last_update: str


class CommoditiesResponse(BaseModel):
    count: int
    source: str
    last_update: str
    commodities: List[CommodityItem]


@router.get("/realtime", response_model=CommoditiesResponse)
async def get_commodities_realtime():
    """
    获取大宗商品实时价格

    Returns:
        黄金、白银、铜、原油的实时行情数据
    """
    import yfinance as yf

    try:
        symbols = list(COMMODITY_SYMBOLS.keys())
        tickers = yf.Tickers(" ".join(symbols))

        commodities: List[CommodityItem] = []

        for symbol in symbols:
            meta = COMMODITY_SYMBOLS[symbol]
            try:
                ticker = tickers.tickers[symbol]
                info = ticker.fast_info

                price = float(info.last_price) if hasattr(info, 'last_price') and info.last_price else 0
                prev_close = float(info.previous_close) if hasattr(info, 'previous_close') and info.previous_close else 0
                open_price = float(info.open) if hasattr(info, 'open') and info.open else 0
                day_high = float(info.day_high) if hasattr(info, 'day_high') and info.day_high else 0
                day_low = float(info.day_low) if hasattr(info, 'day_low') and info.day_low else 0

                change = price - prev_close if prev_close > 0 else 0
                change_pct = (change / prev_close * 100) if prev_close > 0 else 0

                commodities.append(CommodityItem(
                    symbol=symbol,
                    name=meta["name"],
                    name_cn=meta["name_cn"],
                    unit=meta["unit"],
                    price=round(price, 4),
                    change=round(change, 4),
                    change_pct=round(change_pct, 2),
                    high_24h=round(day_high, 4),
                    low_24h=round(day_low, 4),
                    open_price=round(open_price, 4),
                    prev_close=round(prev_close, 4),
                    last_update=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                ))
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")
                # Return a placeholder with zeros so the frontend still renders
                commodities.append(CommodityItem(
                    symbol=symbol,
                    name=meta["name"],
                    name_cn=meta["name_cn"],
                    unit=meta["unit"],
                    price=0,
                    change=0,
                    change_pct=0,
                    high_24h=0,
                    low_24h=0,
                    open_price=0,
                    prev_close=0,
                    last_update=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                ))

        return CommoditiesResponse(
            count=len(commodities),
            source="yahoo_finance",
            last_update=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            commodities=commodities,
        )

    except Exception as e:
        logger.exception("Failed to fetch commodities data")
        raise HTTPException(status_code=500, detail=f"获取大宗商品数据失败: {str(e)}")
