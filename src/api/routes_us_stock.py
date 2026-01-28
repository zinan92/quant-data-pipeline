"""
美股 API 路由
"""
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from src.services.us_stock import get_us_stock_service

router = APIRouter()


class QuoteItem(BaseModel):
    symbol: str
    name: str
    cn_name: str = ""
    price: float
    change: float
    change_pct: float
    volume: int = 0
    market_cap: int = 0
    pe_ratio: float = 0
    last_update: str = ""


class QuotesResponse(BaseModel):
    count: int
    quotes: List[QuoteItem]


class KlineItem(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class KlineResponse(BaseModel):
    symbol: str
    period: str
    interval: str
    count: int
    klines: List[KlineItem]


@router.get("/quote/{symbol}")
async def get_us_stock_quote(symbol: str):
    """
    获取单个美股报价
    
    - **symbol**: 股票代码 (如 AAPL, NVDA, ^GSPC)
    """
    service = get_us_stock_service()
    quote = service.get_quote(symbol.upper())
    
    if not quote:
        raise HTTPException(status_code=404, detail=f"Quote not found for {symbol}")
    
    return quote


@router.get("/quotes")
async def get_us_stock_quotes(
    symbols: str = Query(..., description="股票代码，逗号分隔 (如 AAPL,NVDA,TSLA)")
):
    """
    批量获取美股报价
    """
    service = get_us_stock_service()
    symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    
    quotes = []
    for symbol in symbol_list:
        quote = service.get_quote(symbol)
        if quote:
            quotes.append(quote)
    
    return QuotesResponse(count=len(quotes), quotes=quotes)


@router.get("/indexes", response_model=QuotesResponse)
async def get_us_indexes():
    """获取美股主要指数 (S&P 500, 道琼斯, 纳斯达克等)"""
    service = get_us_stock_service()
    quotes = service.get_indexes()
    return QuotesResponse(count=len(quotes), quotes=quotes)


@router.get("/china-adr", response_model=QuotesResponse)
async def get_china_adr():
    """获取中概股 (阿里, 拼多多, 京东等)"""
    service = get_us_stock_service()
    quotes = service.get_china_adr()
    return QuotesResponse(count=len(quotes), quotes=quotes)


@router.get("/tech", response_model=QuotesResponse)
async def get_tech_stocks():
    """获取科技股 (苹果, 微软, 谷歌等)"""
    service = get_us_stock_service()
    quotes = service.get_tech_stocks()
    return QuotesResponse(count=len(quotes), quotes=quotes)


@router.get("/ai", response_model=QuotesResponse)
async def get_ai_stocks():
    """获取AI概念股 (英伟达, AMD, 微软等)"""
    service = get_us_stock_service()
    quotes = service.get_ai_stocks()
    return QuotesResponse(count=len(quotes), quotes=quotes)


@router.get("/watchlist/{name}", response_model=QuotesResponse)
async def get_watchlist(name: str):
    """
    获取指定监控列表的报价
    
    - **name**: 监控列表名 (indexes/tech/china_adr/ai)
    """
    service = get_us_stock_service()
    quotes = service.get_watchlist_quotes(name)
    
    if not quotes:
        raise HTTPException(status_code=404, detail=f"Watchlist '{name}' not found or empty")
    
    return QuotesResponse(count=len(quotes), quotes=quotes)


@router.get("/watchlists")
async def get_available_watchlists():
    """获取可用的监控列表"""
    service = get_us_stock_service()
    return service.get_available_watchlists()


@router.get("/kline/{symbol}", response_model=KlineResponse)
async def get_us_stock_kline(
    symbol: str,
    period: str = Query("1mo", description="时间范围 (1d/5d/1mo/3mo/6mo/1y/2y/5y/max)"),
    interval: str = Query("1d", description="K线周期 (1m/5m/15m/30m/1h/1d/1wk/1mo)"),
):
    """
    获取美股K线数据
    
    - **symbol**: 股票代码
    - **period**: 时间范围
    - **interval**: K线周期
    """
    service = get_us_stock_service()
    klines = service.get_kline(symbol.upper(), period=period, interval=interval)
    
    if not klines:
        raise HTTPException(status_code=404, detail=f"Kline data not found for {symbol}")
    
    return KlineResponse(
        symbol=symbol.upper(),
        period=period,
        interval=interval,
        count=len(klines),
        klines=klines
    )


@router.get("/summary")
async def get_market_summary():
    """获取美股市场概览"""
    service = get_us_stock_service()
    return service.get_market_summary()
