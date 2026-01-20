from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field

from src.models import Timeframe


class SymbolMeta(BaseModel):
    ticker: str
    name: str
    total_mv: Optional[float] = Field(default=None, serialization_alias="totalMv")  # 总市值（万元）
    circ_mv: Optional[float] = Field(default=None, serialization_alias="circMv")    # 流通市值（万元）
    pe_ttm: Optional[float] = Field(default=None, serialization_alias="peTtm")      # 市盈率TTM
    pb: Optional[float] = Field(default=None, serialization_alias="pb")             # 市净率
    list_date: Optional[str] = Field(default=None, serialization_alias="listDate")  # 上市日期
    industry_lv1: Optional[str] = Field(default=None, serialization_alias="industryLv1")
    industry_lv2: Optional[str] = Field(default=None, serialization_alias="industryLv2")
    industry_lv3: Optional[str] = Field(default=None, serialization_alias="industryLv3")
    super_category: Optional[str] = Field(default=None, serialization_alias="superCategory")  # 超级行业组
    concepts: List[str] = Field(default_factory=list, serialization_alias="concepts")  # 概念板块列表

    # Company information
    introduction: Optional[str] = None  # 公司介绍
    main_business: Optional[str] = Field(default=None, serialization_alias="mainBusiness")  # 主要业务
    business_scope: Optional[str] = Field(default=None, serialization_alias="businessScope")  # 经营范围
    chairman: Optional[str] = None  # 法人代表
    manager: Optional[str] = None  # 总经理
    reg_capital: Optional[float] = Field(default=None, serialization_alias="regCapital")  # 注册资本(万元)
    setup_date: Optional[str] = Field(default=None, serialization_alias="setupDate")  # 成立日期
    province: Optional[str] = None  # 所在省份
    city: Optional[str] = None  # 所在城市
    website: Optional[str] = None  # 公司网站

    last_sync: datetime = Field(serialization_alias="lastUpdated")

    class Config:
        from_attributes = True
        populate_by_name = True

    @computed_field(return_type=List[str], alias="eastmoneyBoard")
    @property
    def eastmoney_board(self) -> List[str]:
        values = [self.industry_lv1, self.industry_lv2, self.industry_lv3]
        return [value for value in values if value]


class CandlePoint(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float]
    turnover: Optional[float]
    ma5: Optional[float]
    ma10: Optional[float]
    ma20: Optional[float]
    ma50: Optional[float]

    class Config:
        from_attributes = True


class CandleBatchResponse(BaseModel):
    ticker: str
    timeframe: Timeframe
    candles: List[CandlePoint]
