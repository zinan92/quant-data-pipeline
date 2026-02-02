"""Raw Market Event — the fundamental data unit in the Perception Layer.

Every piece of data that enters the Prism system — whether a price tick,
a news article, or a social-media post — is first wrapped in a
``RawMarketEvent`` before being routed to detectors.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ────────────────────────────────────────────────────────────


class EventSource(str, Enum):
    """Known data-source identifiers."""

    TUSHARE = "tushare"
    SINA = "sina"
    AKSHARE = "akshare"
    YAHOO = "yahoo"
    TWITTER = "twitter"
    RSS = "rss"


class EventType(str, Enum):
    """Categories of raw market events."""

    PRICE_UPDATE = "price_update"
    KLINE = "kline"
    INDEX_KLINE = "index_kline"
    NEWS = "news"
    ANOMALY = "anomaly"
    SOCIAL = "social"
    METADATA = "metadata"
    BOARD = "board"


class MarketScope(str, Enum):
    """Market scope for an event."""

    A_SHARE = "a_share"
    US_STOCK = "us_stock"
    GLOBAL = "global"


# ── Model ────────────────────────────────────────────────────────────


class RawMarketEvent(BaseModel):
    """A raw, unprocessed market event from any data source.

    This is the *lingua franca* of the Perception Layer.  Every data
    source adapter produces ``RawMarketEvent`` instances; every detector
    consumes them.

    Attributes:
        event_id: Unique identifier (UUID hex by default).
        source: Which data source produced this event.
        event_type: Category of the event (price, news, etc.).
        market: Market scope (A-share, US, global).
        symbol: Ticker symbol, or ``None`` for macro / broad events.
        data: Raw payload as a dict — schema varies by source & type.
        timestamp: When the event originally occurred.
        received_at: When the Perception Layer received the event.
    """

    event_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Unique event identifier (UUID hex)",
    )
    source: str = Field(
        ...,
        min_length=1,
        description="Data source identifier (e.g. 'tushare', 'sina')",
    )
    event_type: str = Field(
        ...,
        min_length=1,
        description="Event category (e.g. 'kline', 'news')",
    )
    market: str = Field(
        ...,
        min_length=1,
        description="Market scope (e.g. 'a_share', 'us_stock', 'global')",
    )
    symbol: Optional[str] = Field(
        default=None,
        description="Ticker symbol; None for macro / broad-market events",
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw payload — schema varies by source and event_type",
    )
    timestamp: datetime = Field(
        ...,
        description="When the event originally occurred",
    )
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the Perception Layer received the event",
    )

    model_config = {"frozen": False, "use_enum_values": True}

    # ── validators ───────────────────────────────────────────────────

    @field_validator("received_at")
    @classmethod
    def _received_not_before_timestamp(cls, v: datetime, info) -> datetime:
        """received_at should not be before timestamp (warn-level)."""
        ts = info.data.get("timestamp")
        if ts is not None and v < ts:
            # Allow clock skew but nudge received_at to at least timestamp
            return ts
        return v

    # ── helpers ──────────────────────────────────────────────────────

    @property
    def age_seconds(self) -> float:
        """Seconds elapsed since the event was received."""
        return (datetime.now(timezone.utc) - self.received_at).total_seconds()

    def matches_type(self, *event_types: str) -> bool:
        """Return True if this event's type is in the given set."""
        return self.event_type in event_types
