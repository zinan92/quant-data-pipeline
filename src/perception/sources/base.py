"""DataSource — abstract base class for all Perception Layer data sources.

Every data source adapter (Tushare, Sina, AKShare, …) subclasses
``DataSource`` and implements the four async lifecycle methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import List

from src.perception.events import RawMarketEvent
from src.perception.health import HealthMonitor, SourceHealth


# ── Enums ────────────────────────────────────────────────────────────


class SourceType(str, Enum):
    """Classification of a data source by its data delivery pattern."""

    REALTIME = "realtime"
    HISTORICAL = "historical"
    NEWS = "news"
    SOCIAL = "social"


# ── Abstract Base ────────────────────────────────────────────────────


class DataSource(ABC):
    """Abstract interface for a Perception Layer data source.

    Subclasses must implement:
    - ``connect()`` — establish connection / authenticate.
    - ``poll()``    — fetch the latest events.
    - ``disconnect()`` — tear down resources.

    Health tracking is provided automatically via ``HealthMonitor``.

    Attributes:
        name: Unique source identifier (e.g. ``"tushare"``).
        source_type: Category of data this source provides.
    """

    def __init__(self, name: str, source_type: SourceType) -> None:
        self.name = name
        self.source_type = source_type
        self._health_monitor = HealthMonitor(name)

    # ── abstract lifecycle methods ───────────────────────────────────

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the upstream data provider.

        Raises:
            ConnectionError: If the upstream is unreachable.
        """

    @abstractmethod
    async def poll(self) -> List[RawMarketEvent]:
        """Fetch the latest batch of events from the source.

        Returns:
            A list of new ``RawMarketEvent`` instances (may be empty).
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully shut down the connection."""

    # ── health ───────────────────────────────────────────────────────

    def health(self) -> SourceHealth:
        """Return a health snapshot for this source.

        The snapshot is derived from the internal ``HealthMonitor``
        that tracks request successes and failures.
        """
        return self._health_monitor.snapshot()

    @property
    def health_monitor(self) -> HealthMonitor:
        """Access the underlying health monitor (for recording events)."""
        return self._health_monitor

    # ── dunder ───────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} type={self.source_type.value!r}>"
