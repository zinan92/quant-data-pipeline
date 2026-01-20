"""
标准格式常量定义

所有日期、时间、Ticker的格式标准
"""

from zoneinfo import ZoneInfo


class StandardFormats:
    """标准内部格式定义"""

    # 日期格式
    DATE_ISO = "%Y-%m-%d"  # 日线: "2026-01-05"
    DATE_COMPACT = "%Y%m%d"  # 紧凑: "20260105"

    # 日期时间格式
    DATETIME_ISO = "%Y-%m-%d %H:%M:%S"  # 分钟线: "2026-01-05 14:30:00"
    DATETIME_COMPACT = "%Y%m%d%H%M"  # 紧凑: "202601051430"

    # 时区
    TIMEZONE = "Asia/Shanghai"  # 中国股市时区
    TZ = ZoneInfo("Asia/Shanghai")


class TickerFormats:
    """Ticker格式示例"""

    # 内部统一格式
    RAW = "000001"  # 6位纯代码

    # Tushare格式
    TUSHARE_SZ = "000001.SZ"
    TUSHARE_SH = "600519.SH"
    TUSHARE_BJ = "430047.BJ"

    # Sina格式
    SINA_SZ = "sz000001"
    SINA_SH = "sh600519"
    SINA_BJ = "bj430047"

    # 东方财富格式
    EASTMONEY_SZ = "0.000001"
    EASTMONEY_SH = "1.600519"


class TimeframeFormats:
    """K线时间周期格式"""

    DAY = "day"
    MINS_30 = "30m"
    MINS_5 = "5m"
    MINS_1 = "1m"
    WEEK = "week"
    MONTH = "month"


class SymbolTypeFormats:
    """标的类型格式"""

    STOCK = "stock"
    INDEX = "index"
    CONCEPT = "concept"
