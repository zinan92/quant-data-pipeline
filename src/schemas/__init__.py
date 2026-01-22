"""
标准化数据模型
所有外部数据必须经过这些模型转换为内部统一格式
"""

# 原有的schemas (base.py)
from src.schemas.base import (
    CandleBatchResponse,
    CandlePoint,
    SymbolMeta,
)

# 新增的标准化模型 (normalized.py)
from src.schemas.normalized import (
    NormalizedDate,
    NormalizedDateTime,
    NormalizedKline,
    NormalizedTicker,
    normalize_date,
    normalize_datetime,
    normalize_ticker,
    ticker_to_sina,
    ticker_to_tushare,
)

# API响应模型 (api.py)
from src.schemas.api import (
    ErrorResponse,
    SuccessResponse,
    KlineData,
    KlineResponse,
    ScreenshotFileInfo,
    ScreenshotListResponse,
    ScreenshotGenerateResponse,
    SingleScreenshotResponse,
    LatestScreenshotResponse,
    SuperCategoryItem,
    SuperCategoriesResponse,
    BoardStockItem,
    BoardStatsResponse,
    SchedulerJobInfo,
    SchedulerJobsResponse,
    TradingStatusResponse,
    IndexQuoteResponse,
)

__all__ = [
    # Base schemas
    "CandleBatchResponse",
    "CandlePoint",
    "SymbolMeta",
    # Normalized schemas
    "NormalizedDate",
    "NormalizedDateTime",
    "NormalizedKline",
    "NormalizedTicker",
    # Utility functions
    "normalize_date",
    "normalize_datetime",
    "normalize_ticker",
    "ticker_to_sina",
    "ticker_to_tushare",
    # API response schemas
    "ErrorResponse",
    "SuccessResponse",
    "KlineData",
    "KlineResponse",
    "ScreenshotFileInfo",
    "ScreenshotListResponse",
    "ScreenshotGenerateResponse",
    "SingleScreenshotResponse",
    "LatestScreenshotResponse",
    "SuperCategoryItem",
    "SuperCategoriesResponse",
    "BoardStockItem",
    "BoardStatsResponse",
    "SchedulerJobInfo",
    "SchedulerJobsResponse",
    "TradingStatusResponse",
    "IndexQuoteResponse",
]
