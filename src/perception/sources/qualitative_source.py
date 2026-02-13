"""QualitativeSource — polls park-intel for qualitative signals.

Fetches topic_heat (SENTIMENT events) and high-relevance articles
(NEWS events) from the park-intel ``/api/articles/signals`` endpoint.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from src.config import get_settings
from src.perception.events import (
    EventSource,
    EventType,
    MarketScope,
    RawMarketEvent,
)
from src.perception.health import HealthStatus, SourceHealth
from src.perception.sources.base import DataSource, SourceType
from src.services.narrative_mapping import TAG_TICKER_MAP
from src.utils.logging import get_logger

logger = get_logger(__name__)


def _infer_market(tags: List[str]) -> MarketScope:
    """Infer MarketScope from article tags."""
    tag_set = {t.lower() for t in tags} if tags else set()
    if "china-market" in tag_set:
        return MarketScope.CN_STOCK
    if "us-market" in tag_set:
        return MarketScope.US_STOCK
    if "crypto" in tag_set:
        return MarketScope.CRYPTO
    if "commodities" in tag_set:
        return MarketScope.COMMODITY
    return MarketScope.GLOBAL


def _parse_ts(raw: Any) -> datetime:
    """Parse a timestamp string into a datetime."""
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return datetime.now(timezone.utc)


class QualitativeSource(DataSource):
    """Poll park-intel for qualitative signals.

    Converts topic_heat entries into SENTIMENT events and
    high-relevance articles into NEWS events.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

        # Health tracking
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
        return "qualitative"

    @property
    def source_type(self) -> SourceType:
        return SourceType.POLLING

    async def connect(self) -> None:
        if self._client is None:
            base_url = get_settings().park_intel_url.rstrip("/")
            self._client = httpx.AsyncClient(
                base_url=base_url,
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
        """Fetch signals from park-intel and convert to RawMarketEvents."""
        if not self._client:
            await self.connect()
        assert self._client is not None

        self._total_polls += 1
        t0 = time.monotonic()

        try:
            resp = await self._client.get(
                "/api/articles/signals",
                params={"hours": 1, "compare_hours": 1},
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            self._record_error(str(exc))
            # Graceful degradation: return empty list instead of raising
            return []

        events: List[RawMarketEvent] = []
        now = datetime.now(timezone.utc)

        # 1. topic_heat → SENTIMENT events
        for item in payload.get("topic_heat", []):
            momentum_label = item.get("momentum_label", "stable")
            if momentum_label == "stable":
                continue

            tag = item.get("tag", "")
            mapping = TAG_TICKER_MAP.get(tag, {})

            events.append(
                RawMarketEvent(
                    source=EventSource.PARK_INTEL,
                    event_type=EventType.SENTIMENT,
                    market=MarketScope.GLOBAL,
                    symbol=None,
                    data={
                        "tag": tag,
                        "momentum_label": momentum_label,
                        "momentum": item.get("momentum", 0),
                        "current_count": item.get("current_count", 0),
                        "previous_count": item.get("previous_count", 0),
                        "us_tickers": mapping.get("us", []),
                        "cn_concepts": mapping.get("cn", []),
                    },
                    timestamp=now,
                )
            )

        # 2. top_articles (relevance_score >= 4) → NEWS events
        for article in payload.get("top_articles", []):
            score = article.get("relevance_score") or 0
            if score < 4:
                continue

            tags = article.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            events.append(
                RawMarketEvent(
                    source=EventSource.PARK_INTEL,
                    event_type=EventType.NEWS,
                    market=_infer_market(tags),
                    symbol=None,
                    data={
                        "title": article.get("title", ""),
                        "content": article.get("content", ""),
                        "source": article.get("source", ""),
                        "author": article.get("author", ""),
                        "url": article.get("url", ""),
                        "relevance_score": score,
                        "tags": tags,
                        "narrative_tags": article.get("narrative_tags", []),
                    },
                    timestamp=_parse_ts(article.get("collected_at")),
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

    # ── Internal ─────────────────────────────────────────────────────

    def _record_error(self, msg: str) -> None:
        self._consecutive_failures += 1
        self._last_error = datetime.now(timezone.utc)
        self._last_error_msg = msg
        logger.warning("QualitativeSource error: %s", msg)
