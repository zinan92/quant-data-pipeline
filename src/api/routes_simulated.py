"""
模拟交易 API
处理模拟买入/卖出、持仓查询、交易记录等
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.simulated_service import get_simulated_service

router = APIRouter()


# ============ Request/Response Models ============

class BuyRequest(BaseModel):
    ticker: str = Field(..., description="股票代码")
    price: float = Field(..., gt=0, description="买入价格")
    position_pct: float = Field(..., gt=0, le=100, description="仓位百分比(基于剩余现金)")
    note: Optional[str] = Field(None, description="备注")


class SellRequest(BaseModel):
    ticker: str = Field(..., description="股票代码")
    price: float = Field(..., gt=0, description="卖出价格")
    sell_pct: float = Field(..., gt=0, le=100, description="卖出比例(基于持仓)")
    note: Optional[str] = Field(None, description="备注")


class TradeResponse(BaseModel):
    success: bool
    trade_id: Optional[int] = None
    ticker: Optional[str] = None
    stock_name: Optional[str] = None
    shares: Optional[int] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    message: Optional[str] = None
    error: Optional[str] = None


class AccountResponse(BaseModel):
    initial_capital: float
    cash: float
    position_value: float
    total_value: float
    total_pnl: float
    total_pnl_pct: float
    position_count: int


class PositionItem(BaseModel):
    ticker: str
    stock_name: str
    shares: int
    cost_price: float
    cost_amount: float
    current_price: Optional[float]
    current_value: float
    pnl: float
    pnl_pct: float
    position_pct: float
    first_buy_date: str
    holding_days: int


class PositionListResponse(BaseModel):
    positions: list[PositionItem]
    total: int


class TradeHistoryItem(BaseModel):
    id: int
    ticker: str
    stock_name: str
    trade_type: str
    trade_date: str
    trade_price: float
    shares: int
    amount: float
    position_pct: Optional[float]
    realized_pnl: Optional[float]
    realized_pnl_pct: Optional[float]
    note: Optional[str]
    created_at: Optional[str]


class TradeHistoryResponse(BaseModel):
    trades: list[TradeHistoryItem]
    total: int


class PositionCheckResponse(BaseModel):
    has_position: bool
    position: Optional[dict] = None


class PerformanceResponse(BaseModel):
    period: str
    my_return: float
    benchmark: dict
    excess_return: Optional[float]
    win_rate: Optional[float]
    avg_holding_days: Optional[float]


# ============ API Endpoints ============

@router.get("/account", response_model=AccountResponse)
def get_account():
    """获取账户概览"""
    service = get_simulated_service()
    result = service.get_account()

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return AccountResponse(**result)


@router.get("/positions", response_model=PositionListResponse)
def get_positions():
    """获取当前持仓列表"""
    service = get_simulated_service()
    positions = service.get_positions()

    return PositionListResponse(
        positions=[PositionItem(**p) for p in positions],
        total=len(positions)
    )


@router.post("/buy", response_model=TradeResponse)
def buy_stock(request: BuyRequest):
    """模拟买入股票"""
    service = get_simulated_service()
    result = service.buy(
        ticker=request.ticker,
        price=request.price,
        position_pct=request.position_pct,
        note=request.note,
    )

    return TradeResponse(**result)


@router.post("/sell", response_model=TradeResponse)
def sell_stock(request: SellRequest):
    """模拟卖出股票"""
    service = get_simulated_service()
    result = service.sell(
        ticker=request.ticker,
        price=request.price,
        sell_pct=request.sell_pct,
        note=request.note,
    )

    return TradeResponse(**result)


@router.get("/trades", response_model=TradeHistoryResponse)
def get_trades(
    limit: int = Query(50, ge=1, le=500, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    ticker: Optional[str] = Query(None, description="按股票代码筛选"),
):
    """获取交易历史"""
    service = get_simulated_service()
    result = service.get_trades(limit=limit, offset=offset, ticker=ticker)

    return TradeHistoryResponse(
        trades=[TradeHistoryItem(**t) for t in result["trades"]],
        total=result["total"]
    )


@router.get("/check/{ticker}", response_model=PositionCheckResponse)
def check_position(ticker: str):
    """检查是否持有某只股票"""
    service = get_simulated_service()
    result = service.check_position(ticker)

    return PositionCheckResponse(**result)


@router.get("/performance", response_model=PerformanceResponse)
def get_performance(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
):
    """获取收益表现对比"""
    service = get_simulated_service()
    result = service.get_performance(days=days)

    return PerformanceResponse(**result)
