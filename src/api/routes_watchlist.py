"""
Watchlist API routes - 自选股管理
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.auth import verify_api_key
from src.config import get_settings
from src.exceptions import DatabaseError
from src.models import Watchlist, SymbolMetadata
from src.schemas import SymbolMeta
from src.services.watchlist_service import WatchlistService
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class WatchlistAdd(BaseModel):
    """添加到自选的请求"""
    ticker: str


class WatchlistResponse(BaseModel):
    """自选股列表响应"""
    ticker: str
    added_at: str


class WatchlistItemResponse(BaseModel):
    """自选股项目响应（包含股票信息和分类）"""
    ticker: str
    name: str
    category: str | None = "未分类"
    added_at: str
    is_focus: bool = Field(default=False, serialization_alias="isFocus")
    positioning: str | None = Field(default=None, description="公司一句话定位描述")
    # 可选的其他股票信息（使用Field设置序列化别名）
    total_mv: float | None = Field(default=None, serialization_alias="totalMv")
    circ_mv: float | None = Field(default=None, serialization_alias="circMv")
    pe_ttm: float | None = Field(default=None, serialization_alias="peTtm")
    pb: float | None = Field(default=None, serialization_alias="pb")
    industry_lv1: str | None = Field(default=None, serialization_alias="industryLv1")
    sector: str | None = Field(default=None, description="赛道分类")
    concepts: list[str] = []

    class Config:
        from_attributes = True
        populate_by_name = True


@router.get("", response_model=List[WatchlistItemResponse])
def get_watchlist(db: Session = Depends(get_db)):
    """获取自选股列表，返回完整的股票信息和分类"""
    service = WatchlistService(db)
    items = service.get_watchlist_items()
    return [WatchlistItemResponse(**item) for item in items]


@router.post("", status_code=201)
async def add_to_watchlist(
    request: WatchlistAdd,
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """添加股票到自选，并立即更新K线数据"""
    from datetime import datetime
    from src.models import Kline, KlineTimeframe, SymbolType
    from sqlalchemy import desc
    from src.services.kline_updater import KlineUpdater

    try:
        # 检查股票是否存在于元数据表
        symbol = db.query(SymbolMetadata).filter(
            SymbolMetadata.ticker == request.ticker
        ).first()

        if not symbol:
            # 从全量 stock_basic 表查找
            from sqlalchemy import text
            row = db.execute(
                text("SELECT symbol, name, industry, market FROM stock_basic WHERE symbol = :ticker"),
                {"ticker": request.ticker}
            ).mappings().first()

            if not row:
                raise HTTPException(status_code=404, detail="股票不存在")

            # 自动创建 SymbolMetadata 记录
            symbol = SymbolMetadata(
                ticker=row["symbol"],
                name=row["name"],
                industry_lv1=row["industry"] or None,
            )
            db.add(symbol)
            db.flush()

        # 检查是否已经在自选中
        existing = db.query(Watchlist).filter(
            Watchlist.ticker == request.ticker
        ).first()

        if existing:
            raise HTTPException(status_code=400, detail="已在自选列表中")

        # 获取最新收盘价作为买入价格（从 klines 表查询）
        latest_kline = db.query(Kline).filter(
            Kline.symbol_code == request.ticker,
            Kline.symbol_type == SymbolType.STOCK,
            Kline.timeframe == KlineTimeframe.DAY
        ).order_by(desc(Kline.trade_time)).first()

        purchase_price = None
        shares = None
        purchase_date = datetime.now()

        if latest_kline and latest_kline.close:
            purchase_price = float(latest_kline.close)
            # 每个自选股买入10000元
            shares = 10000.0 / purchase_price if purchase_price > 0 else None

        # 添加到自选
        watchlist_item = Watchlist(
            ticker=request.ticker,
            purchase_price=purchase_price,
            purchase_date=purchase_date,
            shares=shares
        )
        db.add(watchlist_item)
        db.commit()

        symbol_name = symbol.name

        # 立即更新该股票的K线数据 (使用同一个session)
        updater = KlineUpdater.create_with_session(db)
        kline_result = await updater.update_single_stock_klines(request.ticker)

        return {
            "message": f"成功添加 {symbol_name} 到自选",
            "purchase_price": purchase_price,
            "shares": shares,
            "kline_updated": kline_result
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("添加自选股失败")
        raise DatabaseError(operation="add_to_watchlist", reason=str(e) if get_settings().debug else "Internal server error")


@router.delete("")
def clear_watchlist(db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    """清空所有自选股"""
    count = db.query(Watchlist).delete()
    return {"message": f"已清空自选，共删除 {count} 只股票", "deleted_count": count}


@router.delete("/{ticker}")
def remove_from_watchlist(ticker: str, db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    """从自选中移除股票"""
    watchlist_item = db.query(Watchlist).filter(
        Watchlist.ticker == ticker
    ).first()

    if not watchlist_item:
        raise HTTPException(status_code=404, detail="不在自选列表中")

    db.delete(watchlist_item)

    return {"message": f"已从自选中移除 {ticker}"}


@router.get("/check/{ticker}")
def check_in_watchlist(ticker: str, db: Session = Depends(get_db)):
    """检查股票是否在自选中"""
    exists = db.query(Watchlist).filter(
        Watchlist.ticker == ticker
    ).first() is not None

    return {"in_watchlist": exists}


@router.get("/portfolio/history")
def get_portfolio_history(db: Session = Depends(get_db)):
    """获取投资组合历史数据（用于绘制净值曲线）"""
    service = WatchlistService(db)
    return service.calculate_portfolio_history()


@router.get("/analytics")
def get_watchlist_analytics(db: Session = Depends(get_db)):
    """获取自选股组合分析数据"""
    service = WatchlistService(db)
    return service.calculate_analytics()


@router.patch("/{ticker}/focus")
def toggle_focus(ticker: str, db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    """切换股票的重点关注状态"""
    watchlist_item = db.query(Watchlist).filter(
        Watchlist.ticker == ticker
    ).first()

    if not watchlist_item:
        raise HTTPException(status_code=404, detail="不在自选列表中")

    # 切换is_focus状态
    current_status = bool(watchlist_item.is_focus) if hasattr(watchlist_item, 'is_focus') else False
    watchlist_item.is_focus = not current_status

    return {
        "message": f"{'已添加到' if not current_status else '已移除'}重点关注",
        "ticker": ticker,
        "is_focus": not current_status
    }


class PositioningUpdate(BaseModel):
    """更新公司定位的请求"""
    positioning: str = Field(..., max_length=256, description="公司一句话定位描述")


@router.patch("/{ticker}/positioning")
def update_positioning(ticker: str, request: PositioningUpdate, db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    """更新股票的一句话定位描述"""
    watchlist_item = db.query(Watchlist).filter(
        Watchlist.ticker == ticker
    ).first()

    if not watchlist_item:
        raise HTTPException(status_code=404, detail="不在自选列表中")

    watchlist_item.positioning = request.positioning

    return {
        "message": f"已更新 {ticker} 的定位描述",
        "ticker": ticker,
        "positioning": request.positioning
    }
