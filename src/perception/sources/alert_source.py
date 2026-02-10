"""AlertSource — fetches market alerts and feeds AnomalyDetector + FlowDetector.

Connects to ``/api/news/market-alerts`` to fetch:
- 涨停板 / 跌停板 events → LIMIT_EVENT → AnomalyDetector
- 大笔买入 / 大笔卖出 → ANOMALY → AnomalyDetector
- Capital flow data → FLOW → FlowDetector

Higher-level source that combines fetch + detection.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from src.perception.detectors.anomaly_detector import AnomalyDetector
from src.perception.detectors.flow_detector import FlowDetector
from src.perception.events import (
    EventSource,
    EventType,
    MarketScope,
    RawMarketEvent,
)
from src.perception.health import HealthStatus, SourceHealth
from src.perception.signals import UnifiedSignal
from src.perception.sources.base import DataSource, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AlertSource(DataSource):
    """Fetch market alerts and run anomaly/flow detection.

    Parameters
    ----------
    base_url : str
        Root URL of the ashare API.
    anomaly_detector : AnomalyDetector | None
        Custom detector; creates a default if None.
    flow_detector : FlowDetector | None
        Custom detector; creates a default if None.
    timeout : float
        HTTP timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        anomaly_detector: Optional[AnomalyDetector] = None,
        flow_detector: Optional[FlowDetector] = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._anomaly_detector = anomaly_detector or AnomalyDetector()
        self._flow_detector = flow_detector or FlowDetector()
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
        return "alerts"

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
        """Fetch market alerts → RawMarketEvents."""
        if not self._client:
            await self.connect()
        assert self._client is not None

        self._total_polls += 1
        t0 = time.monotonic()

        try:
            resp = await self._client.get("/api/news/market-alerts")
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            self._record_error(str(exc))
            raise

        items = (
            payload
            if isinstance(payload, list)
            else payload.get("data", payload.get("alerts", []))
        )

        events = _parse_alert_items(items)

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
        """Poll alerts, run anomaly + flow detection, return signals."""
        events = await self.poll()
        signals: List[UnifiedSignal] = []

        for event in events:
            # Route to appropriate detector(s) based on event type
            etype = event.event_type
            etype_val = etype.value if hasattr(etype, "value") else str(etype)

            if etype_val in ("limit_event", "anomaly", "price_update"):
                sigs = self._anomaly_detector.detect(event)
                signals.extend(sigs)

            if etype_val in ("flow", "board_change"):
                sigs = self._flow_detector.detect(event)
                signals.extend(sigs)

        return signals

    # ── Internal ─────────────────────────────────────────────────────

    def _record_error(self, msg: str) -> None:
        self._consecutive_failures += 1
        self._last_error = datetime.now(timezone.utc)
        self._last_error_msg = msg
        logger.warning("AlertSource error: %s", msg)


# ── Parsing helpers ──────────────────────────────────────────────────


def _parse_alert_items(items: List[Dict[str, Any]]) -> List[RawMarketEvent]:
    """Convert raw alert dicts into typed RawMarketEvents."""
    events: List[RawMarketEvent] = []

    for item in items:
        text = (item.get("title") or "") + " " + (item.get("content") or "")
        alert_type = item.get("type") or item.get("alert_type") or ""
        combined = text + " " + alert_type

        ts = _parse_ts(item.get("datetime") or item.get("time"))
        symbol = item.get("symbol") or item.get("ticker") or item.get("code")

        data: Dict[str, Any] = {
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "raw": item,
        }

        # Classify the alert
        if "封涨停板" in combined or "涨停" in combined:
            data["limit_type"] = "limit_up"
            data["limit_up_count"] = item.get("count", 1)
            event_type = EventType.LIMIT_EVENT
        elif "封跌停板" in combined or "跌停" in combined:
            data["limit_type"] = "limit_down"
            data["limit_down_count"] = item.get("count", 1)
            event_type = EventType.LIMIT_EVENT
        elif "大笔买入" in combined or "大单买入" in combined:
            data["order_side"] = "buy"
            data["order_amount"] = item.get("amount", 0)
            event_type = EventType.ANOMALY
        elif "大笔卖出" in combined or "大单卖出" in combined:
            data["order_side"] = "sell"
            data["order_amount"] = item.get("amount", 0)
            event_type = EventType.ANOMALY
        else:
            event_type = EventType.ANOMALY

        events.append(
            RawMarketEvent(
                source=EventSource.CLS,
                event_type=event_type,
                market=MarketScope.CN_STOCK,
                symbol=symbol,
                data=data,
                timestamp=ts,
            )
        )

    return events


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
