"""Perception Layer — Prism Trading System.

The Perception Layer is responsible for:
1. Ingesting raw market data from multiple sources
2. Normalising it into ``RawMarketEvent`` instances
3. Routing events to detectors that emit ``UnifiedSignal`` objects

Public API::

    from src.perception import (
        RawMarketEvent,
        DataSource,
        SourceType,
        SourceRegistry,
        SourceHealth,
        HealthMonitor,
        Detector,
        PerceptionConfig,
        UnifiedSignal,
    )
"""

from src.perception.config import PerceptionConfig
from src.perception.detectors.base import Detector
from src.perception.events import RawMarketEvent
from src.perception.health import HealthMonitor, SourceHealth
from src.perception.signals import UnifiedSignal
from src.perception.sources.base import DataSource, SourceType
from src.perception.sources.registry import SourceRegistry

__all__ = [
    "RawMarketEvent",
    "DataSource",
    "SourceType",
    "SourceRegistry",
    "SourceHealth",
    "HealthMonitor",
    "Detector",
    "PerceptionConfig",
    "UnifiedSignal",
]
