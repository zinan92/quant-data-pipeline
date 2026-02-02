"""Perception Layer — Data Sources.

Re-exports the core abstractions for convenient imports::

    from src.perception.sources import DataSource, SourceType, SourceRegistry
"""

from src.perception.sources.base import DataSource, SourceType
from src.perception.sources.registry import SourceRegistry

__all__ = ["DataSource", "SourceType", "SourceRegistry"]
