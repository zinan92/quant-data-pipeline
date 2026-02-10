"""AShare API data source — connects to the local ashare REST API.

Provides a unified DataSource interface over:
- ``/api/news/latest``       — latest news headlines
- ``/api/news/market-alerts``— limit-up/down & large block alerts
- ``/api/index/realtime/{code}`` — realtime index quotes
- ``/api/news/smart-alerts/scan`` (POST) — smart alert scanning

All HTTP calls use ``httpx.AsyncClient`` with sensible timeouts.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from src.perception.events import (
    EventSource,
    EventType,
    MarketScope,
    RawMarketEvent,
)
from src.perception.health import HealthStatus, SourceHealth
from src.perception.sources.base import DataSource, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Default index codes to track
DEFAULT_INDEX_CODES = [
    "000001.SH",  # 上证指数
    "399001.SZ",  # 深证成指
    "399006.SZ",  # 创业板指
    "000688.SH",  # 科创50
]


class AShareSource(DataSource):
    """Pull data from the local ashare FastAPI backend.

    Parameters
    ----------
    base_url : str
        Root URL of the ashare API (default ``http://127.0.0.1:8000``).
    news_limit : int
        How many news items to fetch per poll.
    index_codes : list[str] | None
        Index codes to query; defaults to the big-four.
    timeout : float
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        news_limit: int = 50,
        index_codes: Optional[List[str]] = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._news_limit = news_limit
        self._index_codes = index_codes or list(DEFAULT_INDEX_CODES)
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
        return "ashare_api"

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
        """Fetch news, alerts, and index data; return as RawMarketEvents."""
        if not self._client:
            await self.connect()

        self._total_polls += 1
        events: List[RawMarketEvent] = []
        t0 = time.monotonic()

        try:
            news_events = await self._fetch_news()
            events.extend(news_events)
        except Exception as exc:
            logger.warning("AShareSource: news fetch failed: %s", exc)

        try:
            alert_events = await self._fetch_alerts()
            events.extend(alert_events)
        except Exception as exc:
            logger.warning("AShareSource: alerts fetch failed: %s", exc)

        try:
            index_events = await self._fetch_indexes()
            events.extend(index_events)
        except Exception as exc:
            logger.warning("AShareSource: index fetch failed: %s", exc)

        self._last_latency_ms = (time.monotonic() - t0) * 1000

        if events:
            self._consecutive_failures = 0
            self._last_success = datetime.now(timezone.utc)
            self._total_events += len(events)
        else:
            self._consecutive_failures += 1

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

        error_rate = 0.0
        if self._total_polls > 0:
            error_rate = self._consecutive_failures / self._total_polls

        return SourceHealth(
            source_name=self.name,
            status=status,
            latency_ms=self._last_latency_ms,
            error_rate=min(1.0, error_rate),
            last_success=self._last_success,
            last_error=self._last_error,
            last_error_message=self._last_error_msg,
            consecutive_failures=self._consecutive_failures,
            total_polls=self._total_polls,
            total_events=self._total_events,
            uptime_seconds=uptime,
        )

    # ── Internal fetchers ────────────────────────────────────────────

    async def _fetch_news(self) -> List[RawMarketEvent]:
        """GET /api/news/latest?limit=N"""
        assert self._client is not None
        resp = await self._client.get(
            "/api/news/latest", params={"limit": self._news_limit}
        )
        resp.raise_for_status()
        payload = resp.json()

        items = payload if isinstance(payload, list) else payload.get("data", payload.get("items", []))
        events: List[RawMarketEvent] = []

        for item in items:
            ts = _parse_timestamp(item.get("datetime") or item.get("created_at") or item.get("time"))
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
                        "raw": item,
                    },
                    timestamp=ts,
                )
            )

        return events

    async def _fetch_alerts(self) -> List[RawMarketEvent]:
        """GET /api/news/market-alerts"""
        assert self._client is not None
        resp = await self._client.get("/api/news/market-alerts")
        resp.raise_for_status()
        payload = resp.json()

        items = payload if isinstance(payload, list) else payload.get("data", payload.get("alerts", []))
        events: List[RawMarketEvent] = []

        for item in items:
            ts = _parse_timestamp(item.get("datetime") or item.get("time"))
            event_type, data = _parse_alert_item(item)
            events.append(
                RawMarketEvent(
                    source=EventSource.CLS,
                    event_type=event_type,
                    market=MarketScope.CN_STOCK,
                    symbol=item.get("symbol") or item.get("ticker") or item.get("code"),
                    data=data,
                    timestamp=ts,
                )
            )

        return events

    async def _fetch_indexes(self) -> List[RawMarketEvent]:
        """GET /api/index/realtime/{ts_code} for each tracked index."""
        assert self._client is not None
        events: List[RawMarketEvent] = []

        for code in self._index_codes:
            try:
                resp = await self._client.get(f"/api/index/realtime/{code}")
                resp.raise_for_status()
                data = resp.json()

                ts = _parse_timestamp(data.get("datetime") or data.get("time"))
                events.append(
                    RawMarketEvent(
                        source=EventSource.EXCHANGE,
                        event_type=EventType.INDEX_UPDATE,
                        market=MarketScope.CN_INDEX,
                        symbol=code,
                        data={
                            "price": data.get("price") or data.get("close"),
                            "change_pct": data.get("change_pct") or data.get("pct_change"),
                            "volume": data.get("volume"),
                            "amount": data.get("amount"),
                            "open": data.get("open"),
                            "high": data.get("high"),
                            "low": data.get("low"),
                            "close": data.get("close") or data.get("price"),
                            "raw": data,
                        },
                        timestamp=ts,
                    )
                )
            except Exception as exc:
                logger.debug("Failed to fetch index %s: %s", code, exc)

        return events

    async def fetch_smart_alerts(self) -> List[Dict[str, Any]]:
        """POST /api/news/smart-alerts/scan — trigger a smart alert scan.

        Returns the raw JSON response as a list of dicts (or empty list).
        """
        if not self._client:
            await self.connect()
        assert self._client is not None

        try:
            resp = await self._client.post("/api/news/smart-alerts/scan")
            resp.raise_for_status()
            payload = resp.json()
            return payload if isinstance(payload, list) else payload.get("data", [])
        except Exception as exc:
            logger.warning("AShareSource: smart-alerts scan failed: %s", exc)
            return []


# ── Helpers ──────────────────────────────────────────────────────────


def _parse_timestamp(raw: Any) -> datetime:
    """Best-effort timestamp parsing; falls back to utcnow."""
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return datetime.now(timezone.utc)


def _parse_alert_item(item: Dict[str, Any]) -> tuple:
    """Parse a market alert item into (EventType, data_dict).

    Recognises patterns like:
    - 封涨停板 / 涨停  → LIMIT_EVENT
    - 封跌停板 / 跌停  → LIMIT_EVENT
    - 大笔买入 / 大单买入 → ANOMALY (large buy)
    - 大笔卖出 / 大单卖出 → ANOMALY (large sell)
    """
    text = (item.get("title") or "") + " " + (item.get("content") or "")
    alert_type = item.get("type") or item.get("alert_type") or ""

    data: Dict[str, Any] = {
        "title": item.get("title", ""),
        "content": item.get("content", ""),
        "raw": item,
    }

    combined = text + " " + alert_type

    if "涨停" in combined:
        data["limit_type"] = "limit_up"
        data["limit_up_count"] = item.get("count", 1)
        return EventType.LIMIT_EVENT, data

    if "跌停" in combined:
        data["limit_type"] = "limit_down"
        data["limit_down_count"] = item.get("count", 1)
        return EventType.LIMIT_EVENT, data

    if "大笔买入" in combined or "大单买入" in combined:
        data["order_side"] = "buy"
        data["order_amount"] = item.get("amount", 0)
        return EventType.ANOMALY, data

    if "大笔卖出" in combined or "大单卖出" in combined:
        data["order_side"] = "sell"
        data["order_amount"] = item.get("amount", 0)
        return EventType.ANOMALY, data

    # Default: generic anomaly
    return EventType.ANOMALY, data
