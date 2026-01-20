"""
统一K线数据API
提供统一的K线数据访问接口
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from src.models import KlineTimeframe, SymbolType
from src.services.kline_service import KlineService
from src.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


def _parse_symbol_type(symbol_type: str) -> SymbolType:
    """解析标的类型"""
    try:
        return SymbolType(symbol_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效的标的类型: {symbol_type}，支持: stock, index, concept"
        )


def _parse_timeframe(timeframe: str) -> KlineTimeframe:
    """解析时间周期"""
    tf_map = {
        "day": KlineTimeframe.DAY,
        "30m": KlineTimeframe.MINS_30,
        "5m": KlineTimeframe.MINS_5,
        "1m": KlineTimeframe.MINS_1,
    }
    tf = tf_map.get(timeframe)
    if tf is None:
        raise HTTPException(
            status_code=400,
            detail=f"无效的时间周期: {timeframe}，支持: day, 30m, 5m, 1m"
        )
    return tf


@router.get("/{symbol_type}/{symbol_code}")
def get_klines(
    symbol_type: str,
    symbol_code: str,
    timeframe: str = Query(default="day", description="时间周期: day, 30m"),
    limit: int = Query(default=120, ge=10, le=500, description="K线数量"),
    start_date: Optional[str] = Query(default=None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="结束日期 YYYY-MM-DD"),
) -> Dict[str, Any]:
    """
    获取K线数据

    Args:
        symbol_type: 标的类型 (stock/index/concept)
        symbol_code: 标的代码
        timeframe: 时间周期 (day/30m)
        limit: 返回数量
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        K线数据
    """
    sym_type = _parse_symbol_type(symbol_type)
    tf = _parse_timeframe(timeframe)

    try:
        with KlineService() as service:
            result = service.get_klines_with_meta(
                symbol_type=sym_type,
                symbol_code=symbol_code,
                timeframe=tf,
                limit=limit,
            )

            if not result["klines"]:
                raise HTTPException(
                    status_code=404,
                    detail=f"未找到K线数据: {symbol_type}/{symbol_code}"
                )

            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"获取K线数据失败: {symbol_type}/{symbol_code}")
        raise HTTPException(status_code=500, detail=f"获取K线数据失败: {str(e)}")
