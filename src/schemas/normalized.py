"""
标准化数据模型 - 中转站模式

所有外部数据进入系统前，必须经过这些Pydantic模型转换为内部统一格式。

统一格式标准:
- Ticker: 6位代码 (如 000001)
- 日期(日线): ISO格式 UTC+8 (如 2026-01-05)
- 日期时间(分钟线): ISO格式 UTC+8 (如 2026-01-05 14:30:00)
- 时区: Asia/Shanghai (UTC+8)
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import ClassVar, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, field_validator, model_validator


# 中国股市时区
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


class NormalizedTicker(BaseModel):
    """
    标准化Ticker - 所有ticker必须经过此模型

    支持的输入格式:
    - 6位代码: 000001, 600519
    - Tushare后缀: 000001.SZ, 600519.SH
    - Sina前缀: sz000001, sh600519
    - 东方财富格式: 0.000001, 1.600519
    - 短码: 1 -> 000001

    输出: 统一的6位代码

    A-share市场识别:
    - Shanghai Main Board: 600xxx, 601xxx, 603xxx, 605xxx
    - Shenzhen Main Board: 000xxx
    - SME Board (Shenzhen): 002xxx
    - ChiNext (Growth): 300xxx
    - STAR Market (SSE): 688xxx, 689xxx
    - Beijing Stock Exchange: 4xxxxx, 8xxxxx
    """

    # Valid A-share ticker patterns (6 digits starting with specific prefixes)
    VALID_PATTERNS: ClassVar[list[str]] = [
        r"^60[0135]\d{3}$",  # Shanghai Main Board (600xxx, 601xxx, 603xxx, 605xxx)
        r"^000\d{3}$",  # Shenzhen Main Board
        r"^002\d{3}$",  # SME Board
        r"^300\d{3}$",  # ChiNext
        r"^68[89]\d{3}$",  # STAR Market
        r"^[48]\d{5}$",  # Beijing Stock Exchange
    ]

    raw: str  # 6位代码，内部统一格式

    @classmethod
    def is_valid_ashare(cls, ticker: str) -> bool:
        """
        检查ticker是否匹配A股合法模式。

        Args:
            ticker: 6位ticker代码

        Returns:
            True if ticker matches any known A-share pattern
        """
        if not ticker or len(ticker) != 6 or not ticker.isdigit():
            return False
        return any(re.match(p, ticker) for p in cls.VALID_PATTERNS)

    def identify_market(self) -> str:
        """
        识别ticker所属市场/板块。

        Returns:
            市场名称 (e.g., "SSE", "SZSE", "ChiNext", "STAR", "BSE", "Unknown")
        """
        code = self.raw
        if not code or len(code) != 6:
            return "Unknown"

        first_three = code[:3]
        first_two = code[:2]

        if first_three in ("600", "601", "603", "605"):
            return "SSE"  # Shanghai Stock Exchange
        elif first_three == "000":
            return "SZSE"  # Shenzhen Stock Exchange (Main Board)
        elif first_three == "002":
            return "SME"  # Small and Medium Enterprise Board
        elif first_three == "300":
            return "ChiNext"  # Growth Enterprise Market
        elif first_two == "68":
            return "STAR"  # Science and Technology Innovation Board
        elif code[0] in ("4", "8"):
            return "BSE"  # Beijing Stock Exchange
        else:
            return "Unknown"

    @field_validator("raw", mode="before")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        """将任意格式转换为6位代码"""
        if not v:
            raise ValueError("Ticker不能为空")

        v = str(v).strip()

        # 去除后缀: 000001.SZ -> 000001
        v = v.split(".")[0]

        # 去除前缀: sz000001 -> 000001, sh600000 -> 600000
        v = re.sub(r"^(sh|sz|bj)", "", v.lower())

        # 去除东方财富格式: 0.000001 -> 000001
        v = re.sub(r"^\d\.", "", v)

        # 补零: 1 -> 000001
        v = v.zfill(6)

        # 验证格式
        if not v.isdigit() or len(v) != 6:
            raise ValueError(f"无效的Ticker格式: {v}")

        return v

    def to_tushare(self) -> str:
        """转换为Tushare格式: 000001.SZ"""
        if self.raw.startswith("6"):
            return f"{self.raw}.SH"
        elif self.raw.startswith(("4", "8")):
            return f"{self.raw}.BJ"
        else:
            return f"{self.raw}.SZ"

    def to_sina(self) -> str:
        """转换为Sina格式: sz000001"""
        if self.raw.startswith("6"):
            return f"sh{self.raw}"
        elif self.raw.startswith(("4", "8")):
            return f"bj{self.raw}"
        else:
            return f"sz{self.raw}"

    def to_eastmoney(self) -> str:
        """转换为东方财富格式: 0.000001"""
        if self.raw.startswith("6"):
            return f"1.{self.raw}"
        else:
            return f"0.{self.raw}"

    def get_market(self) -> str:
        """获取市场标识: SH/SZ/BJ"""
        if self.raw.startswith("6"):
            return "SH"
        elif self.raw.startswith(("4", "8")):
            return "BJ"
        else:
            return "SZ"

    def __str__(self) -> str:
        return self.raw


class NormalizedDate(BaseModel):
    """
    标准化日期 - 日线K线使用

    支持的输入格式:
    - date对象
    - datetime对象 (取日期部分)
    - Unix timestamp (秒)
    - 字符串 YYYYMMDD: 20260105
    - 字符串 YYYY-MM-DD: 2026-01-05
    - 字符串 YYYYMMDDHHMM: 202601051430 (取日期部分)

    输出: date对象，可转换为ISO格式
    """

    value: date

    @field_validator("value", mode="before")
    @classmethod
    def normalize_date(cls, v) -> date:
        """将任意日期格式转换为date对象"""
        if isinstance(v, date) and not isinstance(v, datetime):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, (int, float)):
            # Unix timestamp (秒)
            return datetime.fromtimestamp(v, tz=TZ_SHANGHAI).date()
        if isinstance(v, str):
            v = v.strip()
            # YYYYMMDD -> date
            if len(v) == 8 and v.isdigit():
                return datetime.strptime(v, "%Y%m%d").date()
            # YYYY-MM-DD -> date
            if len(v) >= 10 and "-" in v:
                return datetime.strptime(v[:10], "%Y-%m-%d").date()
            # YYYYMMDDHHMM -> date (同花顺30分钟格式，取日期部分)
            if len(v) == 12 and v.isdigit():
                return datetime.strptime(v[:8], "%Y%m%d").date()
        raise ValueError(f"无法解析日期: {v}")

    def to_iso(self) -> str:
        """输出ISO格式: YYYY-MM-DD"""
        return self.value.strftime("%Y-%m-%d")

    def to_compact(self) -> str:
        """输出紧凑格式: YYYYMMDD"""
        return self.value.strftime("%Y%m%d")

    def __str__(self) -> str:
        return self.to_iso()


class NormalizedDateTime(BaseModel):
    """
    标准化日期时间 - 分钟级K线使用，统一使用UTC+8时区

    支持的输入格式:
    - datetime对象 (带时区则转换，不带则假定为上海时区)
    - Unix timestamp (秒，假定为UTC)
    - 字符串 YYYYMMDDHHMM: 202601051430 (同花顺格式，假定为上海时间)
    - 字符串 YYYY-MM-DD HH:MM:SS: 2026-01-05 14:30:00
    - 字符串 YYYY-MM-DD HH:MM: 2026-01-05 14:30

    输出: datetime对象 (naive，表示上海时间)
    """

    value: datetime

    @field_validator("value", mode="before")
    @classmethod
    def normalize_datetime(cls, v) -> datetime:
        """将任意日期时间格式转换为datetime对象(上海时区，naive)"""
        if isinstance(v, datetime):
            # 如果有时区信息，转换为上海时区
            if v.tzinfo:
                return v.astimezone(TZ_SHANGHAI).replace(tzinfo=None)
            return v
        if isinstance(v, (int, float)):
            # Unix timestamp 默认为UTC，转换为上海时区
            dt = datetime.fromtimestamp(v, tz=ZoneInfo("UTC"))
            return dt.astimezone(TZ_SHANGHAI).replace(tzinfo=None)
        if isinstance(v, str):
            v = v.strip()
            # YYYYMMDDHHMM -> datetime (同花顺格式，已经是上海时间)
            if len(v) == 12 and v.isdigit():
                return datetime.strptime(v, "%Y%m%d%H%M")
            # YYYY-MM-DD HH:MM:SS
            if len(v) >= 19:
                return datetime.strptime(v[:19], "%Y-%m-%d %H:%M:%S")
            # YYYY-MM-DD HH:MM
            if len(v) >= 16 and " " in v:
                return datetime.strptime(v[:16], "%Y-%m-%d %H:%M")
            # 只有日期，补充时间为00:00:00
            if len(v) == 10 and "-" in v:
                return datetime.strptime(v, "%Y-%m-%d")
            if len(v) == 8 and v.isdigit():
                return datetime.strptime(v, "%Y%m%d")
        raise ValueError(f"无法解析日期时间: {v}")

    def to_iso(self) -> str:
        """输出ISO格式(UTC+8): YYYY-MM-DD HH:MM:SS"""
        return self.value.strftime("%Y-%m-%d %H:%M:%S")

    def to_timestamp(self) -> int:
        """输出Unix时间戳(秒)"""
        dt_with_tz = self.value.replace(tzinfo=TZ_SHANGHAI)
        return int(dt_with_tz.timestamp())

    def to_compact(self) -> str:
        """输出紧凑格式: YYYYMMDDHHMM"""
        return self.value.strftime("%Y%m%d%H%M")

    def to_date(self) -> date:
        """提取日期部分"""
        return self.value.date()

    def __str__(self) -> str:
        return self.to_iso()


class NormalizedKline(BaseModel):
    """
    标准化K线数据

    所有K线数据必须经过此模型标准化后再存储或返回
    """

    symbol_type: str  # stock/index/concept
    symbol_code: str  # 6位代码
    symbol_name: Optional[str] = None
    timeframe: str  # day/30m/5m/1m
    trade_time: str  # ISO格式: YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    amount: float = 0
    # 技术指标
    dif: Optional[float] = None
    dea: Optional[float] = None
    macd: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_all(cls, values: dict) -> dict:
        """标准化所有字段"""
        # 标准化symbol_code
        if "symbol_code" in values and values["symbol_code"]:
            try:
                values["symbol_code"] = NormalizedTicker(raw=values["symbol_code"]).raw
            except ValueError:
                pass  # 保持原值，让后续验证处理

        # 标准化trade_time
        if "trade_time" in values and values["trade_time"]:
            raw_time = values["trade_time"]
            tf = values.get("timeframe", "day")
            try:
                if tf == "day" or tf == "DAY":
                    values["trade_time"] = NormalizedDate(value=raw_time).to_iso()
                else:
                    values["trade_time"] = NormalizedDateTime(value=raw_time).to_iso()
            except ValueError:
                pass  # 保持原值

        # 标准化timeframe
        if "timeframe" in values:
            tf_lower = str(values["timeframe"]).lower()
            tf_map = {
                "day": "day",
                "daily": "day",
                "d": "day",
                "30m": "30m",
                "mins_30": "30m",
                "30min": "30m",
                "5m": "5m",
                "mins_5": "5m",
                "1m": "1m",
                "mins_1": "1m",
            }
            values["timeframe"] = tf_map.get(tf_lower, tf_lower)

        # 标准化symbol_type
        if "symbol_type" in values:
            st_lower = str(values["symbol_type"]).lower()
            st_map = {
                "stock": "stock",
                "index": "index",
                "concept": "concept",
            }
            values["symbol_type"] = st_map.get(st_lower, st_lower)

        return values

    def to_dict(self) -> dict:
        """转换为字典，用于数据库插入"""
        return {
            "symbol_type": self.symbol_type,
            "symbol_code": self.symbol_code,
            "symbol_name": self.symbol_name,
            "timeframe": self.timeframe,
            "trade_time": self.trade_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
            "dif": self.dif,
            "dea": self.dea,
            "macd": self.macd,
        }


# 便捷函数
def normalize_ticker(ticker: str) -> str:
    """快速标准化ticker为6位代码"""
    return NormalizedTicker(raw=ticker).raw


def normalize_date(value) -> str:
    """快速标准化日期为ISO格式"""
    return NormalizedDate(value=value).to_iso()


def normalize_datetime(value) -> str:
    """快速标准化日期时间为ISO格式"""
    return NormalizedDateTime(value=value).to_iso()


def ticker_to_tushare(ticker: str) -> str:
    """快速转换ticker为Tushare格式"""
    return NormalizedTicker(raw=ticker).to_tushare()


def ticker_to_sina(ticker: str) -> str:
    """快速转换ticker为Sina格式"""
    return NormalizedTicker(raw=ticker).to_sina()
