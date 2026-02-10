"""
K线形态匹配 API
"""
from fastapi import APIRouter, Query
from typing import Dict, List, Optional
from pydantic import BaseModel

from src.config import get_settings
from src.exceptions import DatabaseError
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/pattern", tags=["pattern"])


class PatternMatch(BaseModel):
    start_idx: int
    end_idx: int
    similarity: float
    future_return: float
    pattern_start_price: float
    pattern_end_price: float


class PatternAnalysis(BaseModel):
    ticker: str
    pattern_days: int
    similar_count: int
    win_rate: Optional[float]
    avg_return: Optional[float]
    avg_similarity: Optional[float]
    best_match: Optional[PatternMatch]
    matches: List[PatternMatch]
    message: Optional[str] = None


@router.get("/analyze/{ticker}", response_model=PatternAnalysis)
async def analyze_pattern(
    ticker: str,
    pattern_days: int = Query(default=20, ge=5, le=60, description="形态天数")
):
    """
    分析股票K线形态
    
    找出历史上相似的形态，统计后续涨跌概率
    
    Args:
        ticker: 股票代码 (如 000661)
        pattern_days: 形态天数 (5-60天)
    
    Returns:
        - similar_count: 相似形态数量
        - win_rate: 历史胜率 (后续上涨的概率)
        - avg_return: 平均收益率
        - matches: 相似形态详情
    """
    try:
        from src.services.pattern_matcher import analyze_stock_pattern
        result = analyze_stock_pattern(ticker, pattern_days)
        return result
    except Exception as e:
        logger.exception("分析股票K线形态失败")
        raise DatabaseError(operation="analyze_pattern", reason=str(e) if get_settings().debug else "Internal server error")


@router.get("/batch-analyze")
async def batch_analyze_patterns(
    tickers: str = Query(..., description="股票代码,逗号分隔"),
    pattern_days: int = Query(default=20, ge=5, le=60)
):
    """
    批量分析多只股票的形态
    """
    try:
        from src.services.pattern_matcher import analyze_stock_pattern
        
        ticker_list = [t.strip() for t in tickers.split(',')][:10]  # 最多10只
        
        results = []
        for ticker in ticker_list:
            try:
                result = analyze_stock_pattern(ticker, pattern_days)
                results.append(result)
            except Exception as e:
                logger.warning(f"Pattern analysis failed for {ticker}: {e}")
                continue
        
        return {
            'analyzed': len(results),
            'results': results
        }
        
    except Exception as e:
        logger.exception("批量分析K线形态失败")
        raise DatabaseError(operation="batch_analyze_patterns", reason=str(e) if get_settings().debug else "Internal server error")
