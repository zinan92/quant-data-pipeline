"""NewsSource — fetches news from the ashare API and runs KeywordDetector.

Lifecycle:
    1. Poll /api/news/latest
    2. Convert to RawMarketEvents
    3. Feed each event through KeywordDetector
    4. Return matched UnifiedSignals

This is a *higher-level* source that combines data fetching and
detection in one step, suitable for the pipeline orchestrator.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from src.perception.detectors.keyword_detector import KeywordDetector, WatchlistEntry
from src.perception.events import (
    EventSource,
    EventType,
    MarketScope,
    RawMarketEvent,
)
from src.perception.health import HealthStatus, SourceHealth
from src.perception.signals import UnifiedSignal
from src.perception.sources.base import DataSource, SourceType

logger = logging.getLogger(__name__)


class NewsSource(DataSource):
    """Fetch news and detect keyword signals.

    Parameters
    ----------
    base_url : str
        Root URL of the ashare API.
    news_limit : int
        Max number of news items per poll.
    detector : KeywordDetector | None
        Custom detector instance; creates a default one if None.
    timeout : float
        HTTP timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        news_limit: int = 50,
        detector: Optional[KeywordDetector] = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._news_limit = news_limit
        self._detector = detector or KeywordDetector()
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

        # Health
        self._connected = False
        self._total_polls = 0
        self._total_events = 0
        self._consecutive_failures = 0
        self._last_success: Optional[datetime] = None
        self._last_error: Optional[datetime] = None
        self._last_error_msg: Optional[str] = None
        self._start_time: Optional[float] = None
        self._last_latency_ms: Optional[float] = None

    # ── DataSource protocol ──────────────────────────────────────────

    @property
    def name(self) -> str:
        return "news"

    @property
    def source_type(self) -> SourceType:
        return SourceType.POLLING

    async def connect(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )
        self._connected = True
        self._start_time = time.monotonic()

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def poll(self) -> List[RawMarketEvent]:
        """Fetch latest news and return as RawMarketEvents."""
        if not self._client:
            await self.connect()
        assert self._client is not None

        self._total_polls += 1
        t0 = time.monotonic()

        try:
            resp = await self._client.get(
                "/api/news/latest", params={"limit": self._news_limit}
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            self._record_error(str(exc))
            raise

        items = (
            payload
            if isinstance(payload, list)
            else payload.get("data", payload.get("items", []))
        )

        events: List[RawMarketEvent] = []
        for item in items:
            ts = _parse_ts(item.get("datetime") or item.get("created_at") or item.get("time"))
            events.append(
                RawMarketEvent(
                    source=EventSource.CLS,
                    event_type=EventType.NEWS,
                    market=MarketScope.CN_STOCK,
                    symbol=item.get("symbol") or item.get("ticker"),
                    data={
                        "title": item.get("title", ""),
                        "content": item.get("content", ""),
                        "summary": item.get("summary", ""),
                        "source": item.get("source", ""),
                        "url": item.get("url", ""),
                    },
                    timestamp=ts,
                )
            )

        self._last_latency_ms = (time.monotonic() - t0) * 1000
        self._total_events += len(events)
        self._consecutive_failures = 0
        self._last_success = datetime.now(timezone.utc)

        return events

    def health(self) -> SourceHealth:
        if self._consecutive_failures >= 5:
            status = HealthStatus.UNHEALTHY
        elif self._consecutive_failures >= 2:
            status = HealthStatus.DEGRADED
        elif self._connected and self._last_success:
            status = HealthStatus.HEALTHY
        else:
            status = HealthStatus.UNKNOWN

        uptime = None
        if self._start_time is not None:
            uptime = time.monotonic() - self._start_time

        return SourceHealth(
            source_name=self.name,
            status=status,
            latency_ms=self._last_latency_ms,
            error_rate=0.0,
            last_success=self._last_success,
            last_error=self._last_error,
            last_error_message=self._last_error_msg,
            consecutive_failures=self._consecutive_failures,
            total_polls=self._total_polls,
            total_events=self._total_events,
            uptime_seconds=uptime,
        )

    # ── Higher-level: detect signals ─────────────────────────────────

    async def detect_signals(self) -> List[UnifiedSignal]:
        """Poll news, run keyword detection, return signals."""
        events = await self.poll()
        signals: List[UnifiedSignal] = []
        for event in events:
            sigs = self._detector.detect(event)
            signals.extend(sigs)
        return signals

    def update_watchlist(self, entries: List[WatchlistEntry]) -> None:
        """Forward watchlist updates to the keyword detector."""
        self._detector.update_watchlist(entries)

    # ── Internal ─────────────────────────────────────────────────────

    def _record_error(self, msg: str) -> None:
        self._consecutive_failures += 1
        self._last_error = datetime.now(timezone.utc)
        self._last_error_msg = msg
        logger.warning("NewsSource error: %s", msg)


def _parse_ts(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return datetime.now(timezone.utc)
