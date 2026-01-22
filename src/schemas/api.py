"""
API响应Schema定义
用于FastAPI路由的响应模型，提供自动文档生成和类型校验
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ============ 通用响应模型 ============

class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误信息")
    detail: Optional[str] = Field(None, description="详细信息")

    model_config = {"from_attributes": True}


class SuccessResponse(BaseModel):
    """通用成功响应模型"""
    success: bool = Field(True, description="是否成功")
    message: Optional[str] = Field(None, description="提示信息")

    model_config = {"from_attributes": True}


# ============ K线相关响应 ============

class KlineData(BaseModel):
    """K线数据点"""
    datetime: str = Field(..., description="交易时间")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: float = Field(..., description="成交量")
    amount: float = Field(..., description="成交额")
    dif: Optional[float] = Field(None, description="MACD DIF")
    dea: Optional[float] = Field(None, description="MACD DEA")
    macd: Optional[float] = Field(None, description="MACD柱")

    model_config = {"from_attributes": True}


class KlineResponse(BaseModel):
    """K线响应模型"""
    symbol_type: str = Field(..., description="标的类型 (stock/index/concept)")
    symbol_code: str = Field(..., description="标的代码")
    symbol_name: Optional[str] = Field(None, description="标的名称")
    timeframe: str = Field(..., description="时间周期 (day/30m/5m/1m)")
    count: int = Field(..., description="K线数量")
    klines: List[KlineData] = Field(..., description="K线数据列表")

    model_config = {"from_attributes": True}


# ============ 截图相关响应 ============

class ScreenshotFileInfo(BaseModel):
    """截图文件信息"""
    filename: str = Field(..., description="文件名")
    ticker: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    timeframe: str = Field(..., description="时间周期")
    size_kb: float = Field(..., description="文件大小(KB)")
    created_at: str = Field(..., description="创建时间")
    path: str = Field(..., description="文件路径")

    model_config = {"from_attributes": True}


class ScreenshotListResponse(BaseModel):
    """截图列表响应"""
    date: str = Field(..., description="日期 (YYYY-MM-DD)")
    timeframe: Optional[str] = Field(None, description="筛选的时间周期")
    count: int = Field(..., description="截图数量")
    directory: str = Field(..., description="目录路径")
    files: List[ScreenshotFileInfo] = Field(..., description="文件列表")

    model_config = {"from_attributes": True}


class ScreenshotGenerateResponse(BaseModel):
    """批量生成截图响应"""
    success: bool = Field(..., description="是否成功")
    total: int = Field(..., description="总数")
    generated: int = Field(..., description="成功生成数")
    failed: int = Field(..., description="失败数")
    failed_tickers: List[str] = Field(default_factory=list, description="失败的股票代码")
    output_dir: str = Field(..., description="输出目录")
    duration_seconds: float = Field(..., description="耗时(秒)")
    files: List[str] = Field(default_factory=list, description="生成的文件名列表")

    model_config = {"from_attributes": True}


class SingleScreenshotResponse(BaseModel):
    """单个截图生成响应"""
    success: bool = Field(..., description="是否成功")
    ticker: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    timeframe: str = Field(..., description="时间周期")
    filepath: str = Field(..., description="文件路径")

    model_config = {"from_attributes": True}


class LatestScreenshotResponse(BaseModel):
    """最新截图目录响应"""
    date: Optional[str] = Field(None, description="日期 (YYYY-MM-DD)")
    directory: Optional[str] = Field(None, description="目录路径")
    count: int = Field(..., description="截图数量")
    message: Optional[str] = Field(None, description="提示信息")

    model_config = {"from_attributes": True}


# ============ 板块相关响应 ============

class SuperCategoryItem(BaseModel):
    """超级行业组项目"""
    name: str = Field(..., description="超级行业组名称")
    count: int = Field(..., description="股票数量")
    market_value: float = Field(..., description="总市值(万元)")

    model_config = {"from_attributes": True}


class SuperCategoriesResponse(BaseModel):
    """超级行业组列表响应"""
    categories: List[SuperCategoryItem] = Field(..., description="超级行业组列表")
    total: int = Field(..., description="总数")

    model_config = {"from_attributes": True}


class BoardStockItem(BaseModel):
    """板块股票项目"""
    ticker: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    total_mv: Optional[float] = Field(None, description="总市值(万元)")
    pe_ttm: Optional[float] = Field(None, description="市盈率TTM")
    pb: Optional[float] = Field(None, description="市净率")

    model_config = {"from_attributes": True}


class BoardStatsResponse(BaseModel):
    """板块统计响应"""
    board_name: str = Field(..., description="板块名称")
    stock_count: int = Field(..., description="股票数量")
    total_market_value: float = Field(..., description="总市值(万元)")
    avg_pe: Optional[float] = Field(None, description="平均市盈率")
    avg_pb: Optional[float] = Field(None, description="平均市净率")
    stocks: List[BoardStockItem] = Field(..., description="股票列表")

    model_config = {"from_attributes": True}


# ============ 任务调度相关响应 ============

class SchedulerJobInfo(BaseModel):
    """调度任务信息"""
    id: str = Field(..., description="任务ID")
    name: str = Field(..., description="任务名称")
    next_run: Optional[str] = Field(None, description="下次运行时间 (ISO格式)")
    trigger: str = Field(..., description="触发器描述")

    model_config = {"from_attributes": True}


class SchedulerJobsResponse(BaseModel):
    """调度任务列表响应"""
    jobs: List[SchedulerJobInfo] = Field(..., description="任务列表")
    count: int = Field(..., description="任务数量")
    is_running: bool = Field(..., description="调度器是否运行中")

    model_config = {"from_attributes": True}


class TradingStatusResponse(BaseModel):
    """交易状态响应"""
    is_trading_day: bool = Field(..., description="是否交易日")
    is_trading_time: bool = Field(..., description="是否交易时间")
    current_time: str = Field(..., description="当前时间")
    latest_trade_date: Optional[str] = Field(None, description="最近交易日")

    model_config = {"from_attributes": True}


# ============ 指数相关响应 ============

class IndexQuoteResponse(BaseModel):
    """指数行情响应"""
    ts_code: str = Field(..., description="指数代码")
    name: Optional[str] = Field(None, description="指数名称")
    close: float = Field(..., description="最新价")
    change: float = Field(..., description="涨跌额")
    pct_chg: float = Field(..., description="涨跌幅(%)")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    pre_close: Optional[float] = Field(None, description="昨收价")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    trade_date: str = Field(..., description="交易日期")

    model_config = {"from_attributes": True}
