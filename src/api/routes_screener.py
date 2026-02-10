"""
股票筛选器 API
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, List
from pydantic import BaseModel

from src.config import get_settings
from src.exceptions import DatabaseError
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/screener", tags=["screener"])


class ScreenerResult(BaseModel):
    ticker: str
    date: str
    signal: str
    details: Dict = {}


class ScreenerResponse(BaseModel):
    golden_cross: List[ScreenerResult]
    macd_golden_cross: List[ScreenerResult]
    oversold_bounce: List[ScreenerResult]
    total: int


@router.get("/signals", response_model=ScreenerResponse)
async def get_screener_signals():
    """
    获取所有选股信号
    
    返回:
    - golden_cross: MA5/MA10 金叉
    - macd_golden_cross: MACD 金叉
    - oversold_bounce: RSI 超卖反弹
    """
    try:
        from src.services.stock_screener import get_screener_results
        results = get_screener_results()
        
        # 格式化输出
        golden_cross = [ScreenerResult(
            ticker=r['ticker'], 
            date=r['date'], 
            signal=r['signal'],
            details={'ma5': r.get('ma5'), 'ma10': r.get('ma10')}
        ) for r in results.get('golden_cross', [])]
        
        macd_golden_cross = [ScreenerResult(
            ticker=r['ticker'],
            date=r['date'],
            signal=r['signal'],
            details={'dif': r.get('dif'), 'dea': r.get('dea')}
        ) for r in results.get('macd_golden_cross', [])]
        
        oversold_bounce = [ScreenerResult(
            ticker=r['ticker'],
            date=r['date'],
            signal=r['signal'],
            details={'rsi6': r.get('rsi6'), 'prev_rsi6': r.get('prev_rsi6')}
        ) for r in results.get('oversold_bounce', [])]
        
        total = len(golden_cross) + len(macd_golden_cross) + len(oversold_bounce)
        
        return ScreenerResponse(
            golden_cross=golden_cross,
            macd_golden_cross=macd_golden_cross,
            oversold_bounce=oversold_bounce,
            total=total
        )
        
    except Exception as e:
        logger.exception("获取选股信号失败")
        raise DatabaseError(operation="get_screener_signals", reason=str(e) if get_settings().debug else "Internal server error")


@router.get("/ticker/{ticker}")
async def get_ticker_indicators(ticker: str):
    """获取单只股票的技术指标"""
    try:
        from src.services.stock_screener import StockScreener
        screener = StockScreener()
        try:
            result = screener.get_latest_indicators(ticker)
            if not result:
                raise HTTPException(status_code=404, detail=f"No data for {ticker}")
            return result
        finally:
            screener.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取股票技术指标失败")
        raise DatabaseError(operation="get_ticker_indicators", reason=str(e) if get_settings().debug else "Internal server error")
