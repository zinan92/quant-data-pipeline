"""Perception data source abstractions and implementations."""

from src.perception.sources.base import DataSource, SourceType
from src.perception.sources.registry import SourceRegistry
from src.perception.sources.ashare_source import AShareSource
from src.perception.sources.news_source import NewsSource
from src.perception.sources.market_data_source import MarketDataSource
from src.perception.sources.alert_source import AlertSource

__all__ = [
    "DataSource",
    "SourceType",
    "SourceRegistry",
    "AShareSource",
    "NewsSource",
    "MarketDataSource",
    "AlertSource",
]
