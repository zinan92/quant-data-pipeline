"""
美股 API 路由
涵盖：指数、板块、Mag7、商品、债券、外汇、新闻、经济日历
"""
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from src.services.us_stock import get_us_stock_service
from src.services.us_news_service import get_us_news_service
from src.services.us_economic_calendar import get_economic_calendar

router = APIRouter()


# ── 数据模型 ──

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


# ── 单个/批量报价 ──

@router.get("/quote/{symbol}")
async def get_us_stock_quote(symbol: str):
    """获取单个美股报价"""
    service = get_us_stock_service()
    quote = service.get_quote(symbol.upper())
    if not quote:
        raise HTTPException(status_code=404, detail=f"Quote not found for {symbol}")
    return quote


@router.get("/quotes")
async def get_us_stock_quotes(
    symbols: str = Query(..., description="股票代码，逗号分隔 (如 AAPL,NVDA,TSLA)")
):
    """批量获取美股报价"""
    service = get_us_stock_service()
    symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    quotes = []
    for symbol in symbol_list:
        quote = service.get_quote(symbol)
        if quote:
            quotes.append(quote)
    return QuotesResponse(count=len(quotes), quotes=quotes)


# ── 指数 & Mag7 ──

@router.get("/indexes", response_model=QuotesResponse)
async def get_us_indexes():
    """获取美股主要指数 (S&P 500, 道琼斯, 纳斯达克等)"""
    service = get_us_stock_service()
    quotes = service.get_indexes()
    return QuotesResponse(count=len(quotes), quotes=quotes)


@router.get("/mag7", response_model=QuotesResponse)
async def get_mag7():
    """获取科技七巨头 (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA)"""
    service = get_us_stock_service()
    quotes = service.get_mag7()
    return QuotesResponse(count=len(quotes), quotes=quotes)


# ── 板块 ──

@router.get("/sectors")
async def get_all_sectors():
    """获取所有板块概览 (每个板块ETF涨跌 + 股票数)"""
    service = get_us_stock_service()
    sectors = service.get_all_sectors()
    return {"count": len(sectors), "sectors": sectors}


@router.get("/sector/{name}")
async def get_sector_detail(name: str):
    """
    获取单个板块详情 (ETF + 板块内个股)

    可用板块名: mag7, semiconductors, ai_application, robotics, defense,
    lithium_battery, nuclear, utilities, metals_mining, biotech, solar,
    precious_metals, financials, ai_infra, gaming_media, travel, genomics,
    consumer_disc, consumer_staples, space, cybersecurity, quantum,
    communication, healthcare, energy, industrials, materials,
    real_estate, ev_newenergy, crypto_fintech, china_adr
    """
    service = get_us_stock_service()
    if name not in service.WATCHLISTS:
        raise HTTPException(status_code=404, detail=f"Sector '{name}' not found")
    return service.get_sector(name)


# ── 传统板块快捷路由 ──

@router.get("/china-adr", response_model=QuotesResponse)
async def get_china_adr():
    """获取中概股"""
    service = get_us_stock_service()
    quotes = service.get_china_adr()
    return QuotesResponse(count=len(quotes), quotes=quotes)


@router.get("/tech", response_model=QuotesResponse)
async def get_tech_stocks():
    """获取半导体/科技股"""
    service = get_us_stock_service()
    quotes = service.get_tech_stocks()
    return QuotesResponse(count=len(quotes), quotes=quotes)


@router.get("/ai", response_model=QuotesResponse)
async def get_ai_stocks():
    """获取AI概念股"""
    service = get_us_stock_service()
    quotes = service.get_ai_stocks()
    return QuotesResponse(count=len(quotes), quotes=quotes)


# ── 商品/债券/外汇 ──

@router.get("/commodities")
async def get_commodities():
    """获取期货/商品 (黄金、白银、原油、铜、天然气)"""
    service = get_us_stock_service()
    quotes = service.get_commodities()
    return {"count": len(quotes), "commodities": quotes}


@router.get("/bonds")
async def get_bonds():
    """获取美债收益率 (5Y/10Y/30Y)"""
    service = get_us_stock_service()
    quotes = service.get_bonds()
    return {"count": len(quotes), "bonds": quotes}


@router.get("/forex")
async def get_forex():
    """获取外汇 (美元指数)"""
    service = get_us_stock_service()
    quotes = service.get_forex()
    return {"count": len(quotes), "forex": quotes}


# ── 新闻 ──

@router.get("/news")
async def get_us_news(
    limit: int = Query(15, ge=1, le=50, description="返回条数")
):
    """获取美股财经快讯 (RSS 聚合: CNBC, MarketWatch, Yahoo Finance)"""
    news_service = get_us_news_service()
    items = news_service.get_news(limit=limit)
    return {"count": len(items), "news": items}


# ── 经济日历 ──

@router.get("/calendar")
async def get_economic_calendar_api(
    days: int = Query(14, ge=1, le=90, description="未来几天"),
    importance: int = Query(1, ge=1, le=3, description="最低重要性 (1=全部, 2=中高, 3=仅高)")
):
    """获取经济日历 (FOMC, CPI, PPI, NFP, GDP, PCE 等)"""
    cal = get_economic_calendar()
    events = cal.get_upcoming(days=days, importance_min=importance)
    return {"count": len(events), "events": events}


# ── 通用 watchlist ──

@router.get("/watchlist/{name}", response_model=QuotesResponse)
async def get_watchlist(name: str):
    """获取指定监控列表的报价"""
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


# ── K线 ──

@router.get("/kline/{symbol}", response_model=KlineResponse)
async def get_us_stock_kline(
    symbol: str,
    period: str = Query("1mo", description="时间范围 (1d/5d/1mo/3mo/6mo/1y/2y/5y/max)"),
    interval: str = Query("1d", description="K线周期 (1m/5m/15m/30m/1h/1d/1wk/1mo)"),
):
    """获取美股K线数据"""
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


# ── 市场概览 ──

@router.get("/summary")
async def get_market_summary():
    """获取美股市场概览 (指数+Mag7+板块ETF+商品+债券+中概股)"""
    service = get_us_stock_service()
    return service.get_market_summary()
