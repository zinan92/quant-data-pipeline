"""
K线截图API路由
提供批量生成截图、获取截图列表等功能
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.services.screenshot_service import ScreenshotService
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class GenerateRequest(BaseModel):
    """生成截图请求"""
    scope: str = Field(default="watchlist", description="范围: watchlist 或 custom")
    tickers: Optional[List[str]] = Field(default=None, description="自定义股票列表")
    timeframe: str = Field(default="day", description="时间周期: day/30m/5m/1m")
    limit: int = Field(default=120, ge=20, le=500, description="K线数量")
    include_volume: bool = Field(default=True, description="是否包含成交量")
    include_macd: bool = Field(default=True, description="是否包含MACD")


@router.post("/generate")
async def generate_screenshots(request: GenerateRequest):
    """
    批量生成K线截图

    - scope=watchlist: 生成所有自选股的截图
    - scope=custom: 生成指定股票列表的截图
    """
    try:
        service = ScreenshotService()
        result = service.batch_generate(
            scope=request.scope,
            tickers=request.tickers,
            timeframe=request.timeframe,
            limit=request.limit,
            include_volume=request.include_volume,
            include_macd=request.include_macd,
        )

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("生成截图失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_screenshots(
    date: Optional[str] = None,
    timeframe: Optional[str] = None,
):
    """
    获取截图列表

    - date: 日期 (YYYY-MM-DD)，默认今天
    - timeframe: 筛选时间周期
    """
    try:
        service = ScreenshotService()
        result = service.list_screenshots(date_str=date, timeframe=timeframe)
        return result

    except Exception as e:
        logger.exception("获取截图列表失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest")
async def get_latest_screenshots():
    """获取最新的截图目录信息"""
    try:
        service = ScreenshotService()
        result = service.get_latest_directory()

        if result is None:
            return {
                "date": None,
                "directory": None,
                "count": 0,
                "message": "暂无截图"
            }

        return result

    except Exception as e:
        logger.exception("获取最新截图目录失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate/single/{ticker}")
async def generate_single_screenshot(
    ticker: str,
    timeframe: str = "day",
    limit: int = 120,
    db: Session = Depends(get_db),
):
    """
    生成单只股票的截图

    - ticker: 股票代码
    - timeframe: 时间周期
    - limit: K线数量
    """
    try:
        from src.models import SymbolMetadata

        # 获取股票名称
        meta = db.query(SymbolMetadata).filter(SymbolMetadata.ticker == ticker).first()
        if not meta:
            raise HTTPException(status_code=404, detail=f"股票 {ticker} 不存在")
        name = meta.name or ticker

        # 生成截图
        service = ScreenshotService()
        filepath = service.generate_chart(
            ticker=ticker,
            name=name,
            timeframe=timeframe,
            limit=limit,
        )

        if filepath is None:
            raise HTTPException(status_code=500, detail=f"生成截图失败，可能没有K线数据")

        return {
            "success": True,
            "ticker": ticker,
            "name": name,
            "timeframe": timeframe,
            "filepath": filepath,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"生成 {ticker} 截图失败")
        raise HTTPException(status_code=500, detail=str(e))
