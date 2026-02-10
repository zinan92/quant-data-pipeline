"""MarketDataSource — realtime market data from indexes and the watchlist DB.

Fetches:
1. Realtime index quotes via ``/api/index/realtime/{code}``
2. Watchlist tickers from ``data/market.db`` → ``watchlist`` table
3. Kline history from ``data/market.db`` → ``klines`` table

Feeds data into PriceDetector, VolumeDetector, and TechnicalDetector
by constructing RawMarketEvents with ``data["bars"]`` payloads.
"""

from __future__ import annotations

from sqlalchemy import text
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

DEFAULT_INDEX_CODES = [
    "000001.SH",
    "399001.SZ",
    "399006.SZ",
    "000688.SH",
]

def _get_default_db_path() -> str:
    from src.config import get_settings
    return str(get_settings().data_dir / "market.db")

DEFAULT_DB_PATH = None  # Resolved lazily

# How many recent kline bars to load per symbol for detector analysis
KLINE_BAR_LIMIT = 260  # ~1 year of daily


class MarketDataSource(DataSource):
    """Combine index API + local DB into RawMarketEvents.

    Parameters
    ----------
    base_url : str
        ashare API base URL.
    db_path : str
        Path to the SQLite market.db.
    index_codes : list[str] | None
        Indexes to track.
    kline_timeframe : str
        Timeframe to pull from klines table (e.g. "daily").
    timeout : float
        HTTP timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        db_path: Optional[str] = None,
        index_codes: Optional[List[str]] = None,
        kline_timeframe: str = "daily",
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._db_path = db_path or _get_default_db_path()
        self._index_codes = index_codes or list(DEFAULT_INDEX_CODES)
        self._kline_timeframe = kline_timeframe
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
        return "market_data"

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
        """Fetch index data + watchlist klines → RawMarketEvents."""
        if not self._client:
            await self.connect()

        self._total_polls += 1
        events: List[RawMarketEvent] = []
        t0 = time.monotonic()

        try:
            idx_events = await self._fetch_index_events()
            events.extend(idx_events)
        except Exception as exc:
            logger.warning("MarketDataSource: index fetch failed: %s", exc)

        try:
            kline_events = self._load_watchlist_klines()
            events.extend(kline_events)
        except Exception as exc:
            logger.warning("MarketDataSource: kline load failed: %s", exc)

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

    # ── Index fetching ───────────────────────────────────────────────

    async def _fetch_index_events(self) -> List[RawMarketEvent]:
        """GET /api/index/realtime/{code} for each tracked index."""
        assert self._client is not None
        events: List[RawMarketEvent] = []

        for code in self._index_codes:
            try:
                resp = await self._client.get(f"/api/index/realtime/{code}")
                resp.raise_for_status()
                data = resp.json()

                ts = _parse_ts(data.get("datetime") or data.get("time"))

                events.append(
                    RawMarketEvent(
                        source=EventSource.EXCHANGE,
                        event_type=EventType.PRICE_UPDATE,
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
                        },
                        timestamp=ts,
                    )
                )
            except Exception as exc:
                logger.debug("MarketDataSource: index %s failed: %s", code, exc)

        return events

    # ── Watchlist + Klines from DB ───────────────────────────────────

    def get_watchlist(self) -> List[Dict[str, Any]]:
        """Read the watchlist table from SQLite."""
        from src.database import SessionLocal

        session = SessionLocal()
        try:
            rows = session.execute(
                text("SELECT ticker, category, is_focus FROM watchlist ORDER BY is_focus DESC")
            ).mappings().fetchall()
            return [dict(r) for r in rows]
        finally:
            session.close()

    def get_klines(self, symbol_code: str, limit: int = KLINE_BAR_LIMIT) -> List[Dict[str, Any]]:
        """Load recent kline bars for a symbol from SQLite."""
        from src.database import SessionLocal

        session = SessionLocal()
        try:
            rows = session.execute(
                text("""
                SELECT trade_time, open, high, low, close, volume, amount
                FROM klines
                WHERE symbol_code = :symbol_code AND timeframe = :timeframe
                ORDER BY trade_time ASC
                LIMIT :limit
                """),
                {"symbol_code": symbol_code, "timeframe": self._kline_timeframe, "limit": limit},
            ).mappings().fetchall()
            return [dict(r) for r in rows]
        finally:
            session.close()

    def _load_watchlist_klines(self) -> List[RawMarketEvent]:
        """Build KLINE events for each watchlist ticker using DB data."""
        watchlist = self.get_watchlist()
        events: List[RawMarketEvent] = []

        for entry in watchlist:
            ticker = entry["ticker"]
            bars = self.get_klines(ticker)
            if not bars:
                continue

            # Detectors expect data["bars"] as list of dicts with
            # keys: open, high, low, close, volume
            bar_dicts = [
                {
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "volume": b["volume"],
                    "amount": b.get("amount", 0),
                }
                for b in bars
            ]

            # Latest bar timestamp
            latest_time = bars[-1].get("trade_time", "")
            ts = _parse_ts(latest_time)

            events.append(
                RawMarketEvent(
                    source=EventSource.EXCHANGE,
                    event_type=EventType.KLINE,
                    market=MarketScope.CN_STOCK,
                    symbol=ticker,
                    data={
                        "bars": bar_dicts,
                        "category": entry.get("category", ""),
                        "is_focus": entry.get("is_focus", 0),
                        "today": bar_dicts[-1] if bar_dicts else {},
                    },
                    timestamp=ts,
                )
            )

        return events


# ── Helpers ──────────────────────────────────────────────────────────


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
