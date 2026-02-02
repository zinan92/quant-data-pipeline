"""Detector — abstract base class for event detectors.

A detector examines ``RawMarketEvent`` instances and, when it
recognises a pattern, emits one or more ``UnifiedSignal`` objects
for downstream consumers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from src.perception.events import RawMarketEvent
from src.perception.signals import UnifiedSignal


class Detector(ABC):
    """Abstract interface for a Perception Layer detector.

    Subclasses must implement ``detect()`` which maps raw events to
    trading signals.

    Attributes:
        name: Unique detector identifier (e.g. ``"volume_spike"``).
        accepts: List of ``event_type`` strings this detector can
            process.  The orchestrator uses this to route events.
    """

    def __init__(self, name: str, accepts: List[str]) -> None:
        self.name = name
        self.accepts = accepts

    def can_handle(self, event: RawMarketEvent) -> bool:
        """Return True if this detector accepts the given event type.

        Args:
            event: The raw event to check.

        Returns:
            ``True`` if ``event.event_type`` is in ``self.accepts``.
        """
        return event.event_type in self.accepts

    @abstractmethod
    async def detect(self, event: RawMarketEvent) -> List[UnifiedSignal]:
        """Analyse a raw event and emit zero or more signals.

        Args:
            event: The incoming raw market event.

        Returns:
            A (possibly empty) list of ``UnifiedSignal`` instances.
        """

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} name={self.name!r} "
            f"accepts={self.accepts!r}>"
        )
